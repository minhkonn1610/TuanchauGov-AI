from pathlib import Path
import re
import shutil
import uuid
from typing import Literal

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.graph.neo4j_store import Neo4jGraphStore
from app.memory.longterm.core import MemoryCore
from app.memory.longterm.neo4j_memory_store import Neo4jMemoryStore
from app.memory.shortterm import ShortTermMemoryService
from app.pipeline.ingest import IngestPipeline
from app.pipeline.naive_chat import NaiveChatPipeline
from app.pipeline.local_chat import LocalChatPipeline
from app.reasoning.deepsearch import DeepSearchPipeline


ROOT_DIR = Path(__file__).resolve().parents[1]
RAW_PDF_DIR = ROOT_DIR / "data" / "raw" / "pdf"
WEB_DIR = ROOT_DIR / "web"

app = FastAPI(title="Chat With TB")
app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")

_ingest_pipeline: IngestPipeline | None = None
_naive_pipeline: NaiveChatPipeline | None = None
_local_pipeline: LocalChatPipeline | None = None
_deep_pipeline: DeepSearchPipeline | None = None
_document_store: Neo4jGraphStore | None = None
_short_memory: ShortTermMemoryService | None = None
_long_memory: MemoryCore | None = None


class ChatRequest(BaseModel):
    query: str
    session_id: str = Field(..., min_length=1, max_length=128)
    top_k: int = 5
    document_ids: list[str] = Field(default_factory=list)
    mode: Literal["fast", "balanced", "deep"] = "fast"


class ConversationCreateRequest(BaseModel):
    session_id: str | None = Field(default=None, max_length=128)
    title: str | None = Field(default=None, max_length=160)
    document_ids: list[str] = Field(default_factory=list)


class ConversationUpdateRequest(BaseModel):
    title: str | None = Field(default=None, max_length=160)
    document_ids: list[str] | None = None


def get_ingest_pipeline() -> IngestPipeline:
    global _ingest_pipeline
    if _ingest_pipeline is None:
        _ingest_pipeline = IngestPipeline.from_config()
    return _ingest_pipeline


def get_naive_pipeline() -> NaiveChatPipeline:
    global _naive_pipeline
    if _naive_pipeline is None:
        _naive_pipeline = NaiveChatPipeline.from_config()
    return _naive_pipeline


def get_local_pipeline() -> LocalChatPipeline:
    global _local_pipeline
    if _local_pipeline is None:
        _local_pipeline = LocalChatPipeline.from_config()
    return _local_pipeline


def get_deep_pipeline() -> DeepSearchPipeline:
    global _deep_pipeline
    if _deep_pipeline is None:
        _deep_pipeline = DeepSearchPipeline.from_config()
    return _deep_pipeline


def get_document_store() -> Neo4jGraphStore:
    global _document_store
    if _document_store is None:
        _document_store = Neo4jGraphStore.from_config()
    return _document_store


def get_short_memory() -> ShortTermMemoryService:
    global _short_memory
    if _short_memory is None:
        _short_memory = ShortTermMemoryService()
    return _short_memory


def get_long_memory() -> MemoryCore:
    global _long_memory
    if _long_memory is None:
        _long_memory = MemoryCore.from_config()
        _long_memory.initialize()
    return _long_memory


def clean_session_id(session_id: str) -> str:
    value = session_id.strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", value):
        raise HTTPException(status_code=400, detail="session_id is invalid.")
    return value


def clean_document_ids(document_ids: list[str]) -> list[str]:
    return list(dict.fromkeys(did.strip() for did in document_ids if did.strip()))


def clean_conversation_title(title: str | None, session_id: str) -> str:
    value = " ".join((title or "").strip().split())
    return value[:120] or f"TB {session_id}"


def conversation_response(conversation: dict, messages: list[dict] | None = None) -> dict:
    document_ids = clean_document_ids(conversation.get("documentIds") or [])
    documents = get_document_store().get_documents_by_ids(document_ids) if document_ids else []
    return {
        "conversation": conversation,
        "messages": messages if messages is not None else get_short_memory().get_history(conversation["sessionId"]),
        "documents": documents,
    }


def delete_long_memory_session(session_id: str) -> dict:
    if _long_memory is not None:
        return _long_memory.delete_session(session_id)
    store = Neo4jMemoryStore.from_config()
    try:
        return store.delete_session(session_id)
    finally:
        store.close()


@app.get("/")
def index():
    return FileResponse(WEB_DIR / "index.html")


@app.get("/health")
def health():
    return {"status": "ok", "app": "Chat With TB"}


# CHATWITH_TB_EVIDENCE_PRECISION_V05: relevance-focused highlights and viewport coordinates; no LLM calls.
_EVIDENCE_STOPWORDS = {
    "là", "của", "và", "các", "những", "một", "cho", "trong", "với", "tại", "về",
    "theo", "để", "từ", "đến", "này", "đó", "khi", "nào", "gì", "thế", "nào",
    "thì", "mà", "được", "phải", "cần", "đã", "sẽ", "có", "không", "trước",
    "sau", "ngày", "hằng", "hàng", "mỗi", "văn", "bản", "thời", "hạn", "deadline",
    "nhiệm", "vụ", "nội", "dung", "thực", "hiện", "công", "tác", "đơn", "vị",
    "bao", "nhiêu", "nêu", "hãy", "vui", "lòng", "trợ", "lý", "chat",
    "the", "in", "on", "is", "are", "of", "for", "to", "and", "what",
}
_TEMPORAL_PATTERN = re.compile(
    r"(?<!\d)(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{1,2}\s*h\s*\d{0,2}|\d{1,2}:\d{2})(?!\d)",
    re.IGNORECASE,
)
_TEMPORAL_QUESTION_PATTERN = re.compile(
    r"thời\s*hạn|deadline|hạn\s*(?:cuối|chót)|khi\s*nào|bao\s*giờ|ngày\s*nào|mấy\s*giờ",
    re.IGNORECASE,
)
_UNIT_QUESTION_PATTERN = re.compile(
    r"đơn\s*vị|cơ\s*quan|kính\s*gửi|nơi\s*nhận|gửi\s*đến|được\s*gửi|"
    r"những\s*đơn\s*vị|các\s*đơn\s*vị|bao\s*gồm.{0,50}(?:đơn\s*vị|cơ\s*quan)|which\s+units|which\s+agencies|what\s+units|what\s+agencies",
    re.IGNORECASE,
)


def _clean_evidence_text(value: str) -> str:
    value = re.sub(r"<!--\s*page:\d+\s*-->", " ", value or "", flags=re.IGNORECASE)
    value = value.replace("\u00ad", "")
    return re.sub(r"\s+", " ", value).strip()


def _evidence_tokens(value: str) -> set[str]:
    lowered = _clean_evidence_text(value).lower()
    tokens = re.findall(
        r"\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{1,2}\s*h\s*\d{0,2}|\d{1,2}:\d{2}|[^\W_]+",
        lowered,
        flags=re.UNICODE | re.IGNORECASE,
    )
    cleaned = set()
    for token in tokens:
        token = re.sub(r"\s+", "", token)
        if token in _EVIDENCE_STOPWORDS:
            continue
        if len(token) < 2 and not token.isdigit():
            continue
        cleaned.add(token)
    return cleaned


def _canonical_temporal(value: str) -> str:
    value = re.sub(r"\s+", "", value.lower()).replace("-", "/")
    date_match = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{2,4})", value)
    if date_match:
        day, month, year = date_match.groups()
        return f"{int(day):02d}/{int(month):02d}/{year}"
    time_match = re.fullmatch(r"(\d{1,2})h(\d{0,2})", value)
    if time_match:
        hour, minute = time_match.groups()
        return f"{int(hour):02d}:{int(minute or 0):02d}"
    time_match = re.fullmatch(r"(\d{1,2}):(\d{2})", value)
    if time_match:
        hour, minute = time_match.groups()
        return f"{int(hour):02d}:{minute}"
    return value


def _evidence_key(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", _clean_evidence_text(value).lower(), flags=re.UNICODE)).strip()


def _recipient_list_context(value: str) -> str:
    """Return the short section after 'Kính gửi', stopping at the document body."""
    raw = re.sub(r"<!--\s*page:\d+\s*-->", " ", value or "", flags=re.IGNORECASE)
    raw = raw.replace("\u00ad", "")
    match = re.search(r"(?:kính\s*gửi|kinh\s*gui)\s*:?", raw, flags=re.IGNORECASE)
    if not match:
        return ""
    tail = raw[match.end():]
    stop = re.search(
        r"\b(?:thực\s+hiện|căn\s+cứ|v/v|về\s+việc|nội\s+dung|kính\s+đề\s+nghị|trân\s+trọng)\b",
        tail,
        flags=re.IGNORECASE,
    )
    if stop:
        tail = tail[:stop.start()]
    return _clean_evidence_text(tail[:900])


def _evidence_phrase_groups(value: str) -> list[list[str]]:
    """Create compact phrase candidates around clauses; avoid one broad highlight for a whole paragraph."""
    cleaned = _clean_evidence_text(value)
    if not cleaned:
        return []
    segments = [
        part.strip(" \t\r\n-•*·")
        for part in re.split(r"(?<=[.!?;:])\s+", cleaned)
        if part.strip(" \t\r\n-•*·")
    ]
    groups: list[list[str]] = []
    seen_groups: set[str] = set()
    for segment in segments[:80]:
        if segment in seen_groups:
            continue
        seen_groups.add(segment)
        candidates: list[str] = []

        def add(raw: str) -> None:
            phrase = re.sub(r"\s+", " ", raw).strip(" \t\r\n-•*·,:;")
            if len(phrase) < 24:
                return
            if len(phrase) > 180:
                phrase = phrase[:180].rsplit(" ", 1)[0]
            if len(phrase) >= 24 and phrase not in candidates:
                candidates.append(phrase)

        add(segment)
        # Favor phrase windows small enough to avoid highlighting unrelated neighboring clauses.
        for width in (150, 120, 95, 75, 58, 42):
            if len(segment) > width:
                add(segment[:width].rsplit(" ", 1)[0])
        words = segment.split()
        for window in (16, 12, 9, 6):
            if len(words) <= window:
                continue
            stride = max(3, window // 2)
            starts = list(range(0, len(words) - window + 1, stride))
            last_start = len(words) - window
            if starts and starts[-1] != last_start:
                starts.append(last_start)
            for start in starts:
                add(" ".join(words[start:start + window]))
        candidates.sort(key=len)
        if candidates:
            groups.append(candidates)
    return groups


def _compact_quad_cluster(quads):
    """Keep one contiguous occurrence when PyMuPDF finds the same phrase more than once."""
    ordered = sorted(quads or [], key=lambda quad: (quad.rect.y0, quad.rect.x0))
    if len(ordered) <= 1:
        return ordered
    clusters = []
    current = [ordered[0]]
    for quad in ordered[1:]:
        previous = current[-1]
        tolerance = max(14.0, min(quad.rect.height, previous.rect.height) * 1.9)
        if abs(quad.rect.y0 - previous.rect.y0) <= tolerance:
            current.append(quad)
        else:
            clusters.append(current)
            current = [quad]
    clusters.append(current)
    return max(clusters, key=lambda group: (len(group), sum(max(1.0, q.rect.width) for q in group)))


def _scroll_result(pdf_document, applied: bool, page_number: int, quads=None) -> dict:
    """Return page + Chrome PDF viewer scroll position; coordinates are derived from the highlight."""
    safe_page = min(max(int(page_number or 1), 1), pdf_document.page_count)
    top_pt = 0.0
    if quads:
        top_pt = max(0.0, min(quad.rect.y0 for quad in quads) - 54.0)
    # Chrome's #zoom=scale,left,top viewport coordinates are CSS-pixel-like page coordinates.
    # At 100% PDF zoom, convert PDF points (72/in) to CSS pixels (96/in).
    scroll_top = max(0, int(round(top_pt * (96.0 / 72.0))))
    return {"applied": bool(applied), "page": safe_page, "scroll_top": scroll_top}


def _highlight_evidence_in_pdf(
    pdf_document,
    page_start: int,
    page_end: int,
    evidence_text: str,
    focus_text: str = "",
    question_text: str = "",
) -> dict:
    """Rank existing source phrases and return a viewport target. Never call an LLM."""
    fallback_page = min(max(int(page_start or 1), 1), pdf_document.page_count)
    # Build evidence anchors from the PDF text layer, not the truncated frontend excerpt.
    source_end_page = min(max(int(page_end or page_start), fallback_page), pdf_document.page_count, fallback_page + 4)
    source_page_numbers = list(range(fallback_page, source_end_page + 1))
    # Recipient questions may refer to the formal "Kính gửi" section on page 1.
    if _UNIT_QUESTION_PATTERN.search(question_text or "") and 1 not in source_page_numbers:
        source_page_numbers.insert(0, 1)
    source_text_parts = []
    for source_page_number in source_page_numbers:
        try:
            source_page_text = pdf_document[source_page_number - 1].get_text("text") or ""
        except Exception:
            source_page_text = ""
        if source_page_text.strip():
            source_text_parts.append(source_page_text)
    pdf_source_text = "\n".join(source_text_parts)
    # Preserve the previous excerpt path only when the PDF has no readable text layer.
    search_text = pdf_source_text if pdf_source_text.strip() else (evidence_text or "")
    groups = _evidence_phrase_groups(search_text)
    if not groups:
        return _scroll_result(pdf_document, False, fallback_page)

    answer_terms = _evidence_tokens(focus_text)
    question_terms = _evidence_tokens(question_text)
    answer_temporal_order = []
    for match in _TEMPORAL_PATTERN.finditer(focus_text or ""):
        temporal = _canonical_temporal(match.group(0))
        if temporal not in answer_temporal_order:
            answer_temporal_order.append(temporal)
    answer_temporals = set(answer_temporal_order)
    temporal_question = bool(_TEMPORAL_QUESTION_PATTERN.search(question_text or ""))
    units_question = bool(_UNIT_QUESTION_PATTERN.search(question_text or ""))
    recipient_context = _recipient_list_context(search_text) if units_question else ""
    recipient_key = _evidence_key(recipient_context)

    final_page = min(max(int(page_end or page_start), fallback_page), pdf_document.page_count, fallback_page + 4)
    scored_hits: list[dict] = []

    unmatched_candidates: list[dict] = []

    for candidates in groups:
        best_for_group = None
        best_candidate_without_hit = None
        for candidate in candidates:
            candidate_temporals = {
                _canonical_temporal(match.group(0))
                for match in _TEMPORAL_PATTERN.finditer(candidate)
            }
            temporal_overlap = candidate_temporals & answer_temporals
            candidate_key = _evidence_key(candidate)
            in_recipient_list = bool(recipient_key and len(candidate_key) >= 18 and candidate_key in recipient_key)
            candidate_terms = _evidence_tokens(candidate)
            answer_overlap = candidate_terms & answer_terms
            question_overlap = candidate_terms & question_terms

            if temporal_question:
                # Each highlighted phrase must contain exactly one date/time that the answer actually stated.
                # This prevents a long phrase containing 21/09 and 31/10 from highlighting both by accident.
                if not answer_temporals or len(candidate_temporals) != 1 or not temporal_overlap:
                    continue
                score = 25.0 + 6.0 * len(temporal_overlap) + 1.6 * len(answer_overlap) - len(candidate) / 160.0
            elif units_question and recipient_key:
                # If the source has a formal 'Kính gửi' section, use only candidates inside that recipient list.
                if not in_recipient_list or not answer_overlap:
                    continue
                score = 30.0 + 3.0 * len(answer_overlap) - len(candidate) / 250.0
            else:
                if len(answer_overlap) < 2 and len(question_overlap) < 1:
                    continue
                score = 3.0 * len(answer_overlap) + 1.5 * len(question_overlap) - len(candidate) / 180.0

            # CHATWITH_TB_EVIDENCE_ACCURACY_V06: remember the best source phrase even when it is absent from the metadata page range.
            recovery_record = {
                "score": score,
                "length": len(candidate),
                "candidate": candidate,
                "temporals": candidate_temporals,
                "recipient": in_recipient_list,
            }
            if best_candidate_without_hit is None or (
                recovery_record["score"], -recovery_record["length"]
            ) > (best_candidate_without_hit["score"], -best_candidate_without_hit["length"]):
                best_candidate_without_hit = recovery_record

            for page_number in range(fallback_page, final_page + 1):
                page = pdf_document[page_number - 1]
                try:
                    raw_quads = page.search_for(candidate, quads=True)
                except Exception:
                    raw_quads = []
                quads = _compact_quad_cluster(raw_quads)
                if not quads:
                    continue
                record = {
                    "score": score,
                    "length": len(candidate),
                    "page_number": page_number,
                    "page": page,
                    "quads": quads,
                    "temporals": candidate_temporals,
                    "recipient": in_recipient_list,
                }
                if best_for_group is None or (record["score"], -record["length"]) > (best_for_group["score"], -best_for_group["length"]):
                    best_for_group = record
        if best_for_group is not None:
            scored_hits.append(best_for_group)
        elif best_candidate_without_hit is not None:
            unmatched_candidates.append(best_candidate_without_hit)

    # CHATWITH_TB_EVIDENCE_ACCURACY_V06: if a relevant phrase is not on the metadata page(s), search elsewhere in the PDF.
    # This is a local exact-text search, capped to a few candidate phrases and adds no LLM calls.
    if unmatched_candidates:
        recovery_pool = []
        seen_phrases = set()
        for record in sorted(unmatched_candidates, key=lambda item: (-item["score"], item["length"])):
            key = _evidence_key(record["candidate"])
            if not key or key in seen_phrases:
                continue
            seen_phrases.add(key)
            recovery_pool.append(record)

        chosen_recovery = []
        if temporal_question:
            for temporal in answer_temporal_order:
                options = [record for record in recovery_pool if temporal in record["temporals"]]
                if options:
                    best = max(options, key=lambda item: (item["score"], -item["length"]))
                    if best not in chosen_recovery:
                        chosen_recovery.append(best)
                if len(chosen_recovery) >= 5:
                    break
        elif units_question and recipient_key:
            chosen_recovery = [record for record in recovery_pool if record["recipient"]][:6]
        else:
            chosen_recovery = recovery_pool[:4]

        pages_to_search = [
            number for number in range(1, pdf_document.page_count + 1)
            if not (fallback_page <= number <= final_page)
        ]
        pages_to_search.sort(key=lambda number: (abs(number - fallback_page), number))
        for record in chosen_recovery:
            for page_number in pages_to_search:
                page = pdf_document[page_number - 1]
                try:
                    raw_quads = page.search_for(record["candidate"], quads=True)
                except Exception:
                    raw_quads = []
                quads = _compact_quad_cluster(raw_quads)
                if not quads:
                    continue
                scored_hits.append({
                    "score": record["score"],
                    "length": record["length"],
                    "page_number": page_number,
                    "page": page,
                    "quads": quads,
                    "temporals": record["temporals"],
                    "recipient": record["recipient"],
                })
                break

    if not scored_hits:
        return _scroll_result(pdf_document, False, fallback_page)

    selected: list[dict] = []
    if temporal_question:
        # Select one best source phrase per distinct date/time in the answer, in answer order.
        for temporal in answer_temporal_order:
            choices = [hit for hit in scored_hits if temporal in hit["temporals"]]
            if choices:
                choice = max(choices, key=lambda hit: (hit["score"], -hit["length"]))
                if choice not in selected:
                    selected.append(choice)
            if len(selected) >= 5:
                break
    elif units_question and recipient_key:
        # Keep the recipient list as a compact block rather than highlighting later mentions of those units.
        selected = sorted(
            [hit for hit in scored_hits if hit["recipient"]],
            key=lambda hit: (hit["page_number"], min(q.rect.y0 for q in hit["quads"]), -hit["score"]),
        )[:6]
    else:
        # For generic task questions, show one local cluster around the most relevant source phrase.
        best = max(scored_hits, key=lambda hit: (hit["score"], -hit["length"]))
        best_top = min(q.rect.y0 for q in best["quads"])
        selected = [
            hit for hit in scored_hits
            if hit["page_number"] == best["page_number"]
            and abs(min(q.rect.y0 for q in hit["quads"]) - best_top) <= 125.0
            and hit["score"] >= max(1.0, best["score"] * 0.35)
        ]
        selected.sort(key=lambda hit: (min(q.rect.y0 for q in hit["quads"]), -hit["score"]))
        selected = selected[:5] or [best]

    if not selected:
        return _scroll_result(pdf_document, False, fallback_page)

    applied = False
    annotated_rects = set()
    for hit in selected:
        page = hit["page"]
        quads = []
        for quad in hit["quads"]:
            rect_key = (page.number, *(round(v, 1) for v in (quad.rect.x0, quad.rect.y0, quad.rect.x1, quad.rect.y1)))
            if rect_key in annotated_rects:
                continue
            annotated_rects.add(rect_key)
            quads.append(quad)
        if not quads:
            continue
        annotation = page.add_highlight_annot(quads)
        if annotation is not None:
            annotation.update()
            applied = True

    if not applied:
        return _scroll_result(pdf_document, False, fallback_page)

    # Prefer the first answer deadline, the top of the formal recipient list, or the best generic hit.
    if temporal_question:
        focus_hit = selected[0]
    elif units_question and recipient_key:
        focus_hit = min(selected, key=lambda hit: (hit["page_number"], min(q.rect.y0 for q in hit["quads"])))
    else:
        focus_hit = max(selected, key=lambda hit: (hit["score"], -hit["length"]))
    first_top_quads = sorted(focus_hit["quads"], key=lambda quad: (quad.rect.y0, quad.rect.x0))
    return _scroll_result(pdf_document, True, focus_hit["page_number"], first_top_quads)


@app.get("/api/documents/{document_id}/evidence.pdf")
def open_evidence_pdf(
    document_id: str,
    page: int = Query(default=1, ge=1, le=10000),
    page_end: int | None = Query(default=None, ge=1, le=10000),
    text: str = Query(default="", max_length=1800),
    focus: str = Query(default="", max_length=900),
    question: str = Query(default="", max_length=300),
):
    """Open a document PDF by its Neo4j ID and highlight evidence in an in-memory copy."""
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}", document_id):
        raise HTTPException(status_code=400, detail="Mã tài liệu không hợp lệ.")

    try:
        documents = get_document_store().get_documents_by_ids([document_id])
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Không thể tra cứu thông tin tài liệu trong Neo4j.",
        ) from exc

    if not documents:
        raise HTTPException(status_code=404, detail="Không tìm thấy tài liệu trong thư viện.")

    stored_name = str(documents[0].get("file_name") or "")
    file_name = Path(stored_name).name
    if (
        not file_name
        or file_name != stored_name
        or Path(file_name).suffix.lower() != ".pdf"
    ):
        raise HTTPException(status_code=404, detail="Không tìm thấy file PDF hợp lệ cho tài liệu này.")

    raw_root = RAW_PDF_DIR.resolve()
    pdf_path = (raw_root / file_name).resolve()
    if pdf_path.parent != raw_root or not pdf_path.is_file():
        raise HTTPException(
            status_code=404,
            detail="Không tìm thấy PDF gốc trong thư mục lưu tài liệu.",
        )
    try:
        if pdf_path.stat().st_size > 100 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="PDF vượt giới hạn xem trước 100 MB.")
    except OSError as exc:
        raise HTTPException(status_code=404, detail="Không thể truy cập file PDF nguồn.") from exc

    try:
        import pymupdf
    except ModuleNotFoundError as exc:
        raise HTTPException(
            status_code=503,
            detail="Thiếu PyMuPDF trong môi trường backend. Cài gói PyMuPDF theo requirements.txt rồi khởi động lại backend.",
        ) from exc

    try:
        with pymupdf.open(str(pdf_path)) as pdf_document:
            if pdf_document.page_count < 1:
                raise HTTPException(status_code=422, detail="PDF không có trang để xem.")
            # Metadata may contain an out-of-range page from an older ingestion; clamp and recover by text.
            page = min(max(page, 1), pdf_document.page_count)
            end_page = page_end if page_end is not None and page_end >= page else page
            end_page = min(end_page, pdf_document.page_count, page + 4)
            highlight_result = _highlight_evidence_in_pdf(pdf_document, page, end_page, text, focus, question)
            highlighted = bool(highlight_result.get("applied")) if isinstance(highlight_result, dict) else bool(highlight_result)
            evidence_page = int(highlight_result.get("page", page)) if isinstance(highlight_result, dict) else page
            evidence_scroll_top = int(highlight_result.get("scroll_top", 0)) if isinstance(highlight_result, dict) else 0
            pdf_bytes = pdf_document.tobytes(garbage=3, deflate=True)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=422, detail="Không thể mở hoặc dựng PDF nguồn.") from exc

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": 'inline; filename="ChatWithTB-evidence.pdf"',
            "Cache-Control": "no-store",
            "X-Evidence-Highlight": "applied" if highlighted else "not-found",
            "X-Evidence-Page": str(evidence_page),
            "X-Evidence-Scroll-Top": str(evidence_scroll_top),
        },
    )


@app.get("/api/documents")
def list_documents(
    q: str = "",
    limit: int = Query(default=50, ge=1, le=100),
):
    try:
        documents = get_document_store().list_documents(search=q, limit=limit)
        return {"documents": documents}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/conversations")
def list_conversations(limit: int = Query(default=50, ge=1, le=100)):
    try:
        return {"conversations": get_short_memory().list_conversations(limit=limit)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/conversations")
def create_conversation(request: ConversationCreateRequest):
    session_id = clean_session_id(request.session_id or str(uuid.uuid4()))
    title = clean_conversation_title(request.title, session_id)
    try:
        conversation = get_short_memory().save_conversation(
            session_id,
            title=title,
            document_ids=clean_document_ids(request.document_ids),
        )
        return conversation_response(conversation, messages=[])
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/conversations/{session_id}")
def get_conversation(session_id: str):
    session_id = clean_session_id(session_id)
    try:
        conversation = get_short_memory().get_conversation(session_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found.")
        return conversation_response(conversation)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/conversations/{session_id}/open")
def open_conversation(session_id: str):
    session_id = clean_session_id(session_id)
    try:
        short_memory = get_short_memory()
        conversation = short_memory.get_conversation(session_id)
        if not conversation:
            raise HTTPException(status_code=404, detail="Conversation not found.")
        conversation = short_memory.touch_conversation(session_id)
        return conversation_response(conversation)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.patch("/api/conversations/{session_id}")
def update_conversation(session_id: str, request: ConversationUpdateRequest):
    session_id = clean_session_id(session_id)
    try:
        short_memory = get_short_memory()
        conversation = short_memory.get_conversation(session_id)
        if not conversation:
            conversation = short_memory.save_conversation(session_id)
        if request.title is not None:
            conversation = short_memory.rename_conversation(
                session_id,
                clean_conversation_title(request.title, session_id),
            )
        if request.document_ids is not None:
            conversation = short_memory.update_conversation_documents(
                session_id,
                clean_document_ids(request.document_ids),
            )
        return conversation_response(conversation)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.delete("/api/conversations/{session_id}")
def delete_conversation(session_id: str):
    session_id = clean_session_id(session_id)
    try:
        long_term_deleted = delete_long_memory_session(session_id)
        get_short_memory().delete_conversation(session_id)
        return {"deleted": True, "sessionId": session_id, "longTerm": long_term_deleted}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/upload")
def upload_pdf(
    files: list[UploadFile] = File(...),
):
    if not files:
        raise HTTPException(status_code=400, detail="No PDF files uploaded.")

    pipeline = get_ingest_pipeline()

    RAW_PDF_DIR.mkdir(parents=True, exist_ok=True)
    documents = []
    for file in files:
        try:
            file_name = Path(file.filename or "").name
            if not file_name or Path(file_name).suffix.lower() != ".pdf":
                raise HTTPException(status_code=400, detail="Only PDF files are supported.")

            raw_path = RAW_PDF_DIR / file_name
            with raw_path.open("wb") as output:
                shutil.copyfileobj(file.file, output)

            documents.append(pipeline.ingest_pdf(raw_path))
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        finally:
            file.file.close()

    return {"documents": documents}


@app.post("/api/chat")
def chat(request: ChatRequest):
    document_ids = [did.strip() for did in request.document_ids if did.strip()]
    if not document_ids:
        raise HTTPException(status_code=400, detail="Upload at least one PDF before asking.")
    session_id = clean_session_id(request.session_id)

    if request.mode == "deep":
        pipeline = get_deep_pipeline()
    elif request.mode == "balanced":
        pipeline = get_local_pipeline()
    else:
        pipeline = get_naive_pipeline()

    memory_context = None
    try:
        memory_context = {
            "conversation_history": get_short_memory().get_history(session_id),
            "long_term_memories": get_long_memory().recall(request.query, session_id=session_id),
        }
    except Exception:
        # ponytail: memory is supporting context; degrade to no-memory chat instead of failing.
        memory_context = None

    try:
        result = pipeline.chat(
            request.query,
            top_k=request.top_k,
            document_ids=document_ids,
            memory_context=memory_context,
        )
        result["sessionId"] = session_id
        try:
            short_memory = get_short_memory()
            result["conversation"] = short_memory.touch_conversation(session_id, document_ids=document_ids)
            short_memory.add_msg(session_id, "user", request.query)
            short_memory.add_msg(session_id, "assistant", result.get("answer", ""))
        except Exception:
            # ponytail: best-effort save; answer should not fail because Redis history is unavailable.
            result["warnings"] = [*(result.get("warnings") or []), "short_memory_save_unavailable"]
        try:
            get_long_memory().add_exchange(request.query, result.get("answer", ""), session_id=session_id)
        except Exception:
            # ponytail: best-effort save; recall/prompt already served, do not fail the turn.
            result["warnings"] = [*(result.get("warnings") or []), "long_memory_save_unavailable"]
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.on_event("shutdown")
def shutdown():
    if _ingest_pipeline is not None:
        _ingest_pipeline.close()
    if _naive_pipeline is not None:
        _naive_pipeline.close()
    if _local_pipeline is not None:
        _local_pipeline.close()
    if _deep_pipeline is not None:
        _deep_pipeline.close()
    if _document_store is not None:
        _document_store.close()
    if _long_memory is not None:
        _long_memory.close()
