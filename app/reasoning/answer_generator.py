from pathlib import Path
import re
from app.providers.context_compressor import ContextCompressor
from app.providers.litellm_client import LiteLLMClient
from app.memory.config import LIMIT_MESSAGES

# CHATWITH_TB_EVIDENCE_ACCURACY_V06: local evidence-card relevance filter; no LLM calls.
_EVIDENCE_FILTER_STOPWORDS = {
    "là", "của", "và", "các", "những", "một", "cho", "trong", "với", "tại", "về",
    "theo", "để", "từ", "đến", "này", "đó", "khi", "nào", "gì", "thế", "thì", "mà",
    "được", "phải", "cần", "đã", "sẽ", "có", "không", "trước", "sau", "mỗi", "văn",
    "bản", "hãy", "nêu", "vui", "lòng", "trợ", "lý", "about", "what", "which", "the",
    "in", "on", "is", "are", "of", "for", "to", "and", "do", "does", "did", "me",
    "please", "tell", "show", "give", "document", "documents",
}
_EVIDENCE_FILTER_TEMPORAL_PATTERN = re.compile(
    r"(?<!\d)(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{1,2}\s*h\s*\d{0,2}|\d{1,2}:\d{2})(?!\d)",
    re.IGNORECASE,
)
_EVIDENCE_FILTER_TEMPORAL_QUESTION = re.compile(
    r"thời\s*hạn|deadline|hạn\s*(?:cuối|chót)|khi\s*nào|bao\s*giờ|ngày\s*nào|mấy\s*giờ",
    re.IGNORECASE,
)
_EVIDENCE_FILTER_RECIPIENT_QUESTION = re.compile(
    r"kính\s*gửi|nơi\s*nhận|gửi\s*đến|văn\s*bản.{0,50}gửi|đơn\s*vị.{0,30}nào|"
    r"which\s+(?:units|agencies)|what\s+(?:units|agencies)|who\s+(?:is|are)\s+addressed",
    re.IGNORECASE,
)


def _evidence_filter_clean(value: str) -> str:
    value = re.sub(r"<!--\s*page:\d+\s*-->", " ", str(value or ""), flags=re.IGNORECASE)
    value = value.replace("\u00ad", "")
    return re.sub(r"\s+", " ", value).strip()


def _evidence_filter_tokens(value: str) -> set[str]:
    tokens = re.findall(
        r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{1,2}\s*h\s*\d{0,2}|\d{1,2}:\d{2}|[^\W_]+",
        _evidence_filter_clean(value).lower(),
        flags=re.UNICODE | re.IGNORECASE,
    )
    result = set()
    for token in tokens:
        token = re.sub(r"\s+", "", token)
        if token in _EVIDENCE_FILTER_STOPWORDS:
            continue
        if len(token) < 2 and not token.isdigit():
            continue
        result.add(token)
    return result


def _evidence_filter_temporal(value: str) -> set[str]:
    values = set()
    for match in _EVIDENCE_FILTER_TEMPORAL_PATTERN.finditer(value or ""):
        token = re.sub(r"\s+", "", match.group(0).lower()).replace("-", "/")
        date_match = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{2,4})", token)
        if date_match:
            day, month, year = date_match.groups()
            token = f"{int(day):02d}/{int(month):02d}/{year}"
        else:
            time_match = re.fullmatch(r"(\d{1,2})h(\d{0,2})", token)
            if time_match:
                hour, minute = time_match.groups()
                token = f"{int(hour):02d}:{int(minute or 0):02d}"
            else:
                time_match = re.fullmatch(r"(\d{1,2}):(\d{2})", token)
                if time_match:
                    token = f"{int(time_match.group(1)):02d}:{time_match.group(2)}"
        values.add(token)
    return values


def _rank_evidence_chunks(chunks: list[dict], query: str, answer: str, max_items: int = 6) -> list[dict]:
    # Select evidence cards locally; do not modify chunks sent to the answer model.
    if not chunks:
        return []
    max_items = max(1, min(int(max_items or 6), 12))
    query_terms = _evidence_filter_tokens(query)
    answer_terms = _evidence_filter_tokens(answer)
    temporal_question = bool(_EVIDENCE_FILTER_TEMPORAL_QUESTION.search(query or ""))
    recipient_question = bool(_EVIDENCE_FILTER_RECIPIENT_QUESTION.search(query or ""))
    answer_temporals = _evidence_filter_temporal(answer)

    records = []
    for index, chunk in enumerate(chunks):
        if not isinstance(chunk, dict):
            continue
        metadata = chunk.get("metadata") or {}
        content = str(chunk.get("content") or "")
        terms = _evidence_filter_tokens(content)
        query_overlap = query_terms & terms
        answer_overlap = answer_terms & terms
        temporal_overlap = answer_temporals & _evidence_filter_temporal(content)
        formal_recipient = bool(re.search(r"(?:kính\s*gửi|kinh\s*gui)\s*:?\s*", content, flags=re.IGNORECASE))
        score = 3.0 * len(query_overlap) + 1.25 * len(answer_overlap)
        score += 5.0 * len(temporal_overlap)
        if formal_recipient:
            score += 2.0
        records.append({
            "index": index, "chunk": chunk, "metadata": metadata, "content": content,
            "score": score, "query_overlap": query_overlap, "answer_overlap": answer_overlap,
            "temporal_overlap": temporal_overlap, "formal_recipient": formal_recipient,
        })

    if not records:
        return []

    if temporal_question and answer_temporals:
        candidates = [record for record in records if record["temporal_overlap"]]
        records = candidates if candidates else sorted(records, key=lambda record: (-record["score"], record["index"]))[:1]
    elif recipient_question:
        # The header and the addressee list can fall into different chunks; require the header chunk to mention an addressee.
        formal = [
            record for record in records
            if record["formal_recipient"] and len(record["answer_overlap"]) >= 2
        ]
        if formal:
            records = formal
        else:
            qualified = [record for record in records if len(record["answer_overlap"]) >= 2]
            records = qualified if qualified else sorted(records, key=lambda record: (-record["score"], record["index"]))[:1]
    else:
        qualified = [
            record for record in records
            if (len(record["answer_overlap"]) >= 2 and len(record["query_overlap"]) >= 1)
            or (len(record["query_overlap"]) >= 2 and len(record["answer_overlap"]) >= 1)
        ]
        records = qualified if qualified else sorted(records, key=lambda record: (-record["score"], record["index"]))[:1]

    # Stable tie-break: preserve retrieval order when relevance scores are equal.
    records.sort(key=lambda record: (-record["score"], record["index"]))
    selected = []
    seen = set()
    for record in records:
        chunk = record["chunk"]
        metadata = record["metadata"]
        key = (
            metadata.get("document_id"),
            metadata.get("chunk_id") or chunk.get("id"),
            _evidence_filter_clean(record["content"])[:160].lower(),
        )
        if key in seen:
            continue
        seen.add(key)
        selected.append(chunk)
        if len(selected) >= max_items:
            break

    # Conservative fallback: never make a previously answerable turn lose all source cards.
    if not selected:
        selected = [record["chunk"] for record in records[:1]]
    return selected


class AnswerGenerator:
    def __init__(
        self,
        llm_client: LiteLLMClient,
        prompt_path: str = "prompts/answer.vi.md",
        context_compressor: ContextCompressor | None = None,
    ):
        self.llm_client = llm_client
        self.system_prompt = Path(prompt_path).read_text(encoding="utf-8")
        self.context_compressor = context_compressor or ContextCompressor.from_config()

    @classmethod
    def from_config(cls) -> "AnswerGenerator":
        return cls(llm_client=LiteLLMClient())

    def generate(
        self,
        query: str,
        chunks: list[dict],
        chat_mode: str = "naive",
        conversation_history: list[dict] | None = None,
        long_term_memories: list[dict] | None = None,
    ) -> dict:
        if not isinstance(query, str) or not query.strip():
            raise ValueError("query is required")
        if chat_mode not in {"naive", "local"}:
            raise ValueError("chat_mode must be naive or local")
        if not chunks:
            return {
                "answer": "Chưa đủ thông tin trong tài liệu để trả lời câu hỏi này.",
                "evidence": [],
                "warnings": ["no_context"],
            }

        compression_report = self.context_compressor.new_report()
        messages = [
            {"role": "system", "content": self.system_prompt},
            {
                "role": "user",
                "content": self._user_content(
                    query,
                    chat_mode,
                    chunks,
                    conversation_history,
                    long_term_memories,
                    compression_report,
                ),
            },
        ]
        # Generate exactly once; use this existing answer only as a local evidence-filter signal.
        answer = self.llm_client.generate(messages)
        evidence = self._evidence(chunks, query=query, answer=answer)
        warnings = self._warnings(evidence)
        if compression_report["errors"]:
            warnings.append("context_compression_error")

        result = {
            "answer": answer,
            "evidence": evidence,
            "warnings": warnings,
        }
        if compression_report["enabled"]:
            result["contextCompression"] = compression_report
        return result

    def _user_content(
        self,
        query: str,
        chat_mode: str,
        chunks: list[dict],
        conversation_history: list[dict] | None,
        long_term_memories: list[dict] | None,
        compression_report: dict,
    ) -> str:
        parts = [f"CÂU HỎI:\n{query.strip()}", f"CHẾ ĐỘ CHAT:\n{chat_mode}"]
        history_section = self._history_section(conversation_history, query, compression_report)
        if history_section:
            parts.append(history_section)
        memory_section = self._memory_section(long_term_memories, query, compression_report)
        if memory_section:
            parts.append(memory_section)
        parts.append(f"CONTEXT:\n{self._context(chunks, query, chat_mode, compression_report)}")
        return "\n\n".join(parts)

    def _history_section(
        self,
        conversation_history: list[dict] | None,
        query: str,
        compression_report: dict,
    ) -> str | None:
        if not conversation_history:
            return None
        lines = []
        limit_msg = LIMIT_MESSAGES if LIMIT_MESSAGES else 20
        for message in conversation_history[-limit_msg:]:
            role = message.get("role")
            content = (message.get("content") or "").strip()
            if not content:
                continue
            if self.context_compressor.compress_history:
                content = self.context_compressor.compress_text(
                    content,
                    query,
                    "short_history",
                    compression_report,
                )
            label = "Người dùng" if role == "user" else "Trợ lý"
            lines.append(f"- {label}: {content}")
        if not lines:
            return None
        return "LỊCH SỬ HỘI THOẠI:\n" + "\n".join(lines)

    def _memory_section(
        self,
        long_term_memories: list[dict] | None,
        query: str,
        compression_report: dict,
    ) -> str | None:
        if not long_term_memories:
            return None
        lines = []
        for result in long_term_memories:
            memory = result.get("memory") if isinstance(result, dict) else None
            memory = memory or (result if isinstance(result, dict) else None)
            content = (memory.get("content") or "").strip() if memory else ""
            if not content:
                continue
            if self.context_compressor.compress_long_memory:
                content = self.context_compressor.compress_text(
                    content,
                    query,
                    "long_memory",
                    compression_report,
                )
            kind = (memory.get("type") or "Context").strip().capitalize()
            lines.append(f"- [{kind}] {content}")
        if not lines:
            return None
        return "KÝ ỨC DÀI HẠN:\n" + "\n".join(lines)

    def _context(
        self,
        chunks: list[dict],
        query: str,
        chat_mode: str,
        compression_report: dict,
    ) -> str:
        blocks = []
        for index, chunk in enumerate(chunks, start=1):
            metadata = chunk.get("metadata") or {}
            file_name = chunk.get("file_name", "")
            page_start = metadata.get("page_start")
            page_end = metadata.get("page_end")
            if page_start and page_end and page_start != page_end:
                source = f"{file_name}, trang {page_start}-{page_end}"
            elif page_start:
                source = f"{file_name}, trang {page_start}"
            else:
                source = file_name

            blocks.append(
                "\n".join(
                    self._context_lines(
                        index,
                        source,
                        chunk,
                        metadata,
                        query,
                        chat_mode,
                        compression_report,
                    )
                )
            )
        return "\n\n".join(blocks)

    def _context_lines(
        self,
        index: int,
        source: str,
        chunk: dict,
        metadata: dict,
        query: str,
        chat_mode: str,
        compression_report: dict,
    ) -> list[str]:
        lines = [f"[Đoạn {index}] Nguồn: {source}"]
        if chat_mode == "local":
            matched_entities = metadata.get("matched_entities") or []
            relationship_context = (metadata.get("relationship_context") or "").strip()
            community_context = (metadata.get("community_context") or "").strip()
            if matched_entities:
                lines.append(f"Thực thể khớp: {', '.join(matched_entities)}")
            if relationship_context:
                if self.context_compressor.compress_chunks:
                    relationship_context = self.context_compressor.compress_text(
                        relationship_context,
                        query,
                        "relationship_context",
                        compression_report,
                    )
                lines.extend(["Ngữ cảnh quan hệ:", relationship_context])
            if community_context:
                if self.context_compressor.compress_chunks:
                    community_context = self.context_compressor.compress_text(
                        community_context,
                        query,
                        "community_context",
                        compression_report,
                    )
                lines.extend(["Ngữ cảnh cộng đồng:", community_context])
            lines.append("Nội dung đoạn:")
        content = chunk.get("content", "")
        if self.context_compressor.compress_chunks:
            content = self.context_compressor.compress_text(
                content,
                query,
                "chunk",
                compression_report,
            )
        lines.append(content)
        return lines

    @staticmethod
    def _evidence(chunks: list[dict], query: str = "", answer: str = "") -> list[dict]:
        # Filter display-only source cards. The original chunks are still passed unchanged to the LLM.
        selected_chunks = _rank_evidence_chunks(chunks, query=query, answer=answer)
        evidence = []
        for chunk in selected_chunks:
            metadata = chunk.get("metadata") or {}
            evidence.append(
                {
                    "chunkId": chunk.get("id") or metadata.get("chunk_id"),
                    "documentId": metadata.get("document_id"),
                    "fileName": chunk.get("file_name"),
                    "pageStart": metadata.get("page_start"),
                    "pageEnd": metadata.get("page_end"),
                    "text": chunk.get("content", ""),
                    "score": chunk.get("score"),
                    "position": metadata.get("position"),
                    "sectionPath": metadata.get("section_path"),
                }
            )
        return evidence

    @staticmethod
    def _warnings(evidence: list[dict]) -> list[str]:
        if any(item.get("pageStart") is None or item.get("pageEnd") is None for item in evidence):
            return ["page_numbers_unavailable"]
        return []
