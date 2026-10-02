from io import BytesIO
from pypdf import PdfReader
from app.providers.interfaces import Extraction, TextLine, UnsupportedDocument

MAX_UPLOAD = 5 * 1024 * 1024


class LocalPDFExtractor:
    def extract(self, content: bytes) -> Extraction:
        if len(content) > MAX_UPLOAD or not content.startswith(b"%PDF-"):
            raise UnsupportedDocument("unsupported_pdf")
        try:
            reader = PdfReader(BytesIO(content), strict=True)
            if reader.is_encrypted or len(reader.pages) != 1:
                raise UnsupportedDocument("single_page_unencrypted_pdf_required")
            page = reader.pages[0]
            # Mixed image/text packets can omit relevant scanned fields. Fail closed.
            if list(page.images):
                raise UnsupportedDocument("image_content_requires_manual_review")
            text = page.extract_text() or ""
            if not text.strip():
                raise UnsupportedDocument("scanned_or_empty_pdf_requires_manual_review")
            if len(text) > 20000:
                raise UnsupportedDocument("document_text_exceeds_demo_scope")
            return Extraction(
                [TextLine(line.strip()) for line in text.splitlines() if line.strip()]
            )
        except UnsupportedDocument:
            raise
        except Exception:
            raise UnsupportedDocument("unreadable_pdf_requires_manual_review") from None
