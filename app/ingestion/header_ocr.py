from __future__ import annotations

import json
import logging
import math
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

LOGGER = logging.getLogger(__name__)
OCR_PYTHON_ENV = "CHATWITHTB_OCR_PYTHON"
OCR_DPI = 300
OCR_CROP_RATIO = 0.30
OCR_MIN_CONFIDENCE = 0.85
OCR_TIMEOUT_SECONDS = 180
_OFFICIAL_HEADER_CUE_PATTERN = re.compile(
    r"\b(?:ubnd|ủy\s*ban|uỷ\s*ban|bộ|sở|cộng\s*hòa|cộng\s*hoà|"
    r"độc\s*lập|kính\s*gửi|văn\s*phòng|số)\b",
    re.UNICODE | re.IGNORECASE,
)

_DOCUMENT_NUMBER_PATTERN = re.compile(
    r"(?<!\d)(\d{3,}\s*/\s*[\w&.\-]+)",
    re.UNICODE | re.IGNORECASE,
)
_DATE_WORDS_PATTERN = re.compile(
    r"\bngày\s+(\d{1,2})\s+tháng\s+(\d{1,2})\s+năm\s+(\d{4})\b",
    re.UNICODE | re.IGNORECASE,
)
_DATE_NUMERIC_PATTERN = re.compile(
    r"(?<!\d)(\d{1,2})\s*[/.-]\s*(\d{1,2})\s*[/.-]\s*(\d{4})(?!\d)"
)


def missing_header_fields(header_text: str) -> set[str]:
    """Return official-header fields not found in the extractable text of the top crop."""
    text = re.sub(r"\s+", " ", str(header_text or "")).strip()
    missing: set[str] = set()
    if not _DOCUMENT_NUMBER_PATTERN.search(text):
        missing.add("document_number")
    if not _DATE_WORDS_PATTERN.search(text) and not _DATE_NUMERIC_PATTERN.search(text):
        missing.add("date")
    return missing


def select_ocr_header_fields(
    recognized_lines: list[dict[str, Any]],
    min_confidence: float = OCR_MIN_CONFIDENCE,
) -> dict[str, dict[str, Any]]:
    """Select only a document number and date from OCR lines above the confidence floor."""
    selected: dict[str, dict[str, Any]] = {}
    for item in recognized_lines or []:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        try:
            confidence = float(item.get("confidence"))
        except (TypeError, ValueError):
            continue
        if not math.isfinite(confidence) or confidence < min_confidence:
            continue

        if "document_number" not in selected:
            number_match = _DOCUMENT_NUMBER_PATTERN.search(text)
            if number_match:
                value = re.sub(r"\s+", "", number_match.group(1))
                selected["document_number"] = {
                    "value": value,
                    "confidence": confidence,
                    "source_text": text,
                }

        if "date" not in selected:
            date_match = _DATE_WORDS_PATTERN.search(text)
            if date_match:
                day, month, year = (int(part) for part in date_match.groups())
                if _valid_date(day, month, year):
                    selected["date"] = {
                        "value": f"{day:02d}/{month:02d}/{year:04d}",
                        "confidence": confidence,
                        "source_text": text,
                    }
            else:
                date_match = _DATE_NUMERIC_PATTERN.search(text)
                if date_match:
                    day, month, year = (int(part) for part in date_match.groups())
                    if _valid_date(day, month, year):
                        selected["date"] = {
                            "value": f"{day:02d}/{month:02d}/{year:04d}",
                            "confidence": confidence,
                            "source_text": text,
                        }
    return selected


def _valid_date(day: int, month: int, year: int) -> bool:
    if year < 1900 or year > 2200 or month < 1 or month > 12 or day < 1 or day > 31:
        return False
    # Validate the actual calendar date without extra dependencies.
    import datetime

    try:
        datetime.date(year, month, day)
    except ValueError:
        return False
    return True


def _resolve_ocr_python() -> Path | None:
    configured = os.environ.get(OCR_PYTHON_ENV, "").strip().strip('"')
    if configured:
        candidate = Path(configured)
        return candidate if candidate.is_file() else None

    # Option C: keep the OCR runtime in its own environment beside ChatWithTBv2.
    # This removes the runtime dependency on the separate Chairman project.
    project_root = Path(__file__).resolve().parents[2]
    project_ocr_python = project_root / ".venv-ocr" / "Scripts" / "python.exe"
    return project_ocr_python if project_ocr_python.is_file() else None


def _render_top_crop(pdf_path: Path, output_image: Path) -> None:
    """Render only the top 30% of page 1 at 300 DPI using the already-installed PyMuPDF."""
    import pymupdf

    with pymupdf.open(str(pdf_path)) as document:
        if document.page_count < 1:
            raise ValueError("PDF không có trang để OCR.")
        page = document[0]
        rect = page.rect
        clip = pymupdf.Rect(
            rect.x0,
            rect.y0,
            rect.x1,
            rect.y0 + rect.height * OCR_CROP_RATIO,
        )
        pixmap = page.get_pixmap(
            matrix=pymupdf.Matrix(OCR_DPI / 72.0, OCR_DPI / 72.0),
            clip=clip,
            alpha=False,
        )
        pixmap.save(str(output_image))


def _run_ocr(pdf_path: Path) -> dict[str, dict[str, Any]]:
    ocr_python = _resolve_ocr_python()
    if ocr_python is None:
        LOGGER.warning(
            "Header OCR skipped: set %s to a Python interpreter with PaddleOCR installed.",
            OCR_PYTHON_ENV,
        )
        return {}

    worker_path = Path(__file__).with_name("ocr_header_worker.py")
    if not worker_path.is_file():
        LOGGER.warning("Header OCR skipped: worker script is missing.")
        return {}

    with tempfile.TemporaryDirectory(prefix="chatwithtb_header_ocr_") as temp_dir:
        temp_root = Path(temp_dir)
        image_path = temp_root / "header_crop.png"
        output_json = temp_root / "ocr_fields.json"
        try:
            _render_top_crop(pdf_path, image_path)
            command = [
                str(ocr_python), str(worker_path),
                "--image", str(image_path),
                "--output-json", str(output_json),
                "--min-confidence", str(OCR_MIN_CONFIDENCE),
            ]
            env = os.environ.copy()
            env["FLAGS_use_mkldnn"] = "0"
            env["PYTHONIOENCODING"] = "utf-8"
            completed = subprocess.run(
                command,
                cwd=str(pdf_path.parent),
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=OCR_TIMEOUT_SECONDS,
                check=False,
            )
            if completed.returncode != 0:
                LOGGER.warning(
                    "Header OCR worker failed (exit %s): %s",
                    completed.returncode,
                    (completed.stderr or completed.stdout or "No diagnostic output")[-1200:],
                )
                return {}
            if not output_json.is_file():
                LOGGER.warning("Header OCR worker returned no result file.")
                return {}
            payload = json.loads(output_json.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                return {}
            fields = payload.get("fields", {})
            return fields if isinstance(fields, dict) else {}
        except subprocess.TimeoutExpired:
            LOGGER.warning("Header OCR timed out after %s seconds.", OCR_TIMEOUT_SECONDS)
        except Exception as exc:
            LOGGER.warning("Header OCR failed safely: %s", exc)
    return {}


def format_missing_header_additions(
    missing: set[str],
    fields: dict[str, dict[str, Any]],
    min_confidence: float = OCR_MIN_CONFIDENCE,
) -> list[str]:
    """Format OCR values only for fields confirmed absent from the extracted header."""
    lines: list[str] = []
    for key, label in (("document_number", "Số văn bản"), ("date", "Ngày ban hành")):
        if key not in missing:
            continue
        value = fields.get(key)
        if not isinstance(value, dict) or not value.get("value"):
            continue
        try:
            confidence = float(value.get("confidence"))
        except (TypeError, ValueError):
            continue
        if not math.isfinite(confidence) or confidence < min_confidence:
            continue
        lines.append(f"{label} (OCR bổ sung): {value['value']}")
    if not lines:
        return []
    return ["Thông tin đầu văn bản được OCR bổ sung:", *lines]


def supplement_missing_header_fields(
    pdf_path: str | Path,
    header_text: str,
    full_page_text: str,
) -> list[str]:
    """Return only missing header fields. Never prevents normal PDF extraction if OCR fails."""
    missing = missing_header_fields(header_text)
    if not missing:
        return []

    page_text = str(full_page_text or "").strip()
    # Avoid OCR for blank/scanned pages; this narrowly targets mixed PDFs where the body
    # already has a useful text layer but header values are embedded as an image.
    if len(page_text) < 50:
        return []

    # Do not OCR arbitrary first pages. Require cues of an official Vietnamese document.
    cue_text = f"{header_text or ''} {page_text}"
    if not _OFFICIAL_HEADER_CUE_PATTERN.search(cue_text):
        return []

    fields = _run_ocr(Path(pdf_path))
    return format_missing_header_additions(missing, fields)
