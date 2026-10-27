from pathlib import Path

# CHATWITHTB_SELECTIVE_HEADER_OCR_V02: optional OCR in a separate Python environment.
from app.ingestion.header_ocr import supplement_missing_header_fields

class PDFLoader:
    def __init__(self, processed_dir: str | Path = "data/processed"):
        self.processed_dir = Path(processed_dir)
        self.md = self._load_converter()

    def processing(self, pdf_file_path: str) -> str:
        pdf_path = Path(pdf_file_path)
        self._validate_pdf_path(pdf_path)

        # Convert PDF to markdown, retaining page boundaries for citations.
        markdown = self._page_aware_markdown(pdf_path)
        if not markdown:
            markdown = self.md.convert(str(pdf_path)).text_content
        
        self.processed_dir.mkdir(parents=True, exist_ok=True)
        output_path = self.processed_dir / f"{pdf_path.stem}.md"
        output_path.write_text(markdown, encoding="utf-8")
        return markdown

    @staticmethod
    def _page_aware_markdown(pdf_path: Path) -> str:
        try:
            import pdfplumber

            with pdfplumber.open(pdf_path) as pdf:
                pages = []
                for page_number, page in enumerate(pdf.pages, start=1):
                    text = page.extract_text() or ""

                    # CHATWITHTB_SELECTIVE_HEADER_OCR_V02: only inspect the first-page header.
                    # OCR is invoked only when its document number or date is absent from the
                    # extractable top 30%; the body text and all other pages keep the old path.
                    if page_number == 1 and len(text.strip()) >= 50:
                        try:
                            header_crop = page.crop(
                                (0, 0, page.width, page.height * 0.30)
                            )
                            header_text = header_crop.extract_text() or ""
                            additions = supplement_missing_header_fields(
                                pdf_path=pdf_path,
                                header_text=header_text,
                                full_page_text=text,
                            )
                        except Exception:
                            # OCR is a non-blocking enhancement; retain normal extraction on errors.
                            additions = []

                        if additions:
                            text = "\n".join(additions) + "\n\n" + text

                    if text.strip():
                        pages.append(
                            f"<!-- page:{page_number} -->\n\n{text.strip()}"
                        )
        except Exception:
            return ""

        return "\n\n".join(pages)

    @staticmethod
    def _load_converter():
        try:
            from markitdown import MarkItDown
        except ModuleNotFoundError as exc:
            raise RuntimeError("Missing dependency: install markitdown from requirements.txt.") from exc
        return MarkItDown()

    @staticmethod
    def _validate_pdf_path(pdf_path: Path) -> None:
        if pdf_path.suffix.lower() != ".pdf":
            raise ValueError(f"Expected a PDF file, got: {pdf_path}")
        if not pdf_path.exists():
            raise FileNotFoundError(pdf_path)
        if not pdf_path.is_file():
            raise ValueError(f"Expected a file path, got: {pdf_path}")
        if pdf_path.stat().st_size == 0:
            raise ValueError(f"PDF file is empty: {pdf_path}")

    
