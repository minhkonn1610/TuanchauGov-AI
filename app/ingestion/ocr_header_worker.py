from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

# Disable oneDNN/MKLDNN as in the proven Chairman OCR environment.
os.environ["FLAGS_use_mkldnn"] = "0"

# The worker script lives in app/ingestion; make the project root visible so the
# small, standard-library-only selector can be imported without app dependencies.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.ingestion.header_ocr import select_ocr_header_fields  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="OCR only document number/date fields in a header crop.")
    parser.add_argument("--image", required=True)
    parser.add_argument("--output-json", required=True)
    parser.add_argument("--min-confidence", type=float, default=0.85)
    args = parser.parse_args()

    image_path = Path(args.image)
    output_path = Path(args.output_json)
    if not image_path.is_file():
        parser.error("Input header crop does not exist.")

    from paddleocr import PaddleOCR

    ocr = PaddleOCR(lang="vi", device="cpu")
    result = ocr.predict(str(image_path))

    recognized = []
    for page_result in result or []:
        texts = page_result.get("rec_texts", [])
        scores = page_result.get("rec_scores", [])
        for index, text in enumerate(texts):
            score = float(scores[index]) if index < len(scores) else None
            recognized.append({"text": str(text), "confidence": score})

    fields = select_ocr_header_fields(recognized, min_confidence=args.min_confidence)
    output_path.write_text(
        json.dumps({"fields": fields}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
