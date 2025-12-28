"""PDF utility functions for text extraction from attachments."""

from pathlib import Path

from pypdf import PdfReader


def extract_text_from_pdf(pdf_path: str | Path) -> str:
    """Extract all text content from a PDF file.

    Args:
        pdf_path: Path to the PDF file.

    Returns:
        Extracted text as a single string with pages separated by newlines.
    """
    path = Path(pdf_path)
    if not path.exists():
        return ""

    try:
        reader = PdfReader(path)
        pages_text = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                pages_text.append(text.strip())
        return "\n\n".join(pages_text)
    except Exception:
        return ""


def get_pdf_page_count(pdf_path: str | Path) -> int:
    """Get the number of pages in a PDF file.

    Args:
        pdf_path: Path to the PDF file.

    Returns:
        Number of pages, or 0 if the file cannot be read.
    """
    path = Path(pdf_path)
    if not path.exists():
        return 0

    try:
        reader = PdfReader(path)
        return len(reader.pages)
    except Exception:
        return 0


def extract_text_per_page(pdf_path: str | Path) -> list[str]:
    """Extract text from each page of a PDF file.

    Args:
        pdf_path: Path to the PDF file.

    Returns:
        List of strings, one per page. Empty list if file cannot be read.
    """
    path = Path(pdf_path)
    if not path.exists():
        return []

    try:
        reader = PdfReader(path)
        pages_text = []
        for page in reader.pages:
            text = page.extract_text()
            pages_text.append(text.strip() if text else "")
        return pages_text
    except Exception:
        return []


class PDFAttachment:
    """Represents a PDF attachment with extracted content."""

    def __init__(self, path: str | Path, name: str):
        self.path = Path(path)
        self.name = name
        self._text: str | None = None
        self._page_count: int | None = None
        self._pages_text: list[str] | None = None

    @property
    def exists(self) -> bool:
        """Check if the PDF file exists."""
        return self.path.exists()

    @property
    def text(self) -> str:
        """Get full text content (lazily extracted)."""
        if self._text is None:
            self._text = extract_text_from_pdf(self.path)
        return self._text

    @property
    def page_count(self) -> int:
        """Get number of pages (lazily computed)."""
        if self._page_count is None:
            self._page_count = get_pdf_page_count(self.path)
        return self._page_count

    @property
    def pages_text(self) -> list[str]:
        """Get text per page (lazily extracted)."""
        if self._pages_text is None:
            self._pages_text = extract_text_per_page(self.path)
        return self._pages_text

    def __repr__(self) -> str:
        return f"PDFAttachment({self.name!r}, pages={self.page_count})"
