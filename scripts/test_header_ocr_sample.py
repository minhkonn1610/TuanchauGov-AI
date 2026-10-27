from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import tempfile

# Allow running with `python scripts/test_header_ocr_sample.py` from the project root.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in os.sys.path:
    os.sys.path.insert(0, str(PROJECT_ROOT))

from app.ingestion.pdf_loader import PDFLoader  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Safely test selective header OCR without Neo4j or LLM calls.")
    parser.add_argument("--pdf", required=True, help="Path to a local test PDF.")
    args = parser.parse_args()
    pdf_path = Path(args.pdf)
    if not pdf_path.is_file():
        raise FileNotFoundError(pdf_path)

    with tempfile.TemporaryDirectory(prefix="chatwithtb_header_ocr_test_") as output_dir:
        markdown = PDFLoader(processed_dir=output_dir).processing(str(pdf_path))

    has_number = bool(re.search(r"\b12904\b", markdown))
    has_date = bool(re.search(r"22/09/2026", markdown))
    page_marker = "<!-- page:1 -->" in markdown

    print("PDF_LOADER_TEST_COMPLETED: True")
    print(f"OCR_NUMBER_PRESENT: {has_number}")
    print(f"OCR_DATE_PRESENT: {has_date}")
    print(f"PAGE_1_MARKER_PRESERVED: {page_marker}")
    print(f"MARKDOWN_CHARS: {len(markdown)}")
    if has_number and has_date and page_marker:
        print("SELECTIVE_HEADER_OCR_TEST: PASS")
        return 0
    print("SELECTIVE_HEADER_OCR_TEST: INCOMPLETE; review OCR logs/results before reingesting anything.")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
