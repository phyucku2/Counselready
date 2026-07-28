"""PDF text-layer extraction.

This reads the text a PDF already carries. It does not perform OCR: a scanned filing
has no text layer, and the honest outcome for those pages is "we have not read this
yet" rather than an empty string that looks like an empty page.

Everything here is synchronous and CPU-bound, so callers run it off the event loop.
"""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO

from pypdf import PdfReader
from pypdf.errors import PyPdfError

PDF_MAGIC = b"%PDF-"

# A family court file can be long, but a single document past this is a red flag
# rather than a filing, and unbounded page counts are a denial-of-service surface.
DEFAULT_MAX_PAGES = 2000

# Guards against a pathological page whose "text" expands to megabytes.
DEFAULT_MAX_CHARS_PER_PAGE = 200_000


class NotAPdfError(Exception):
    """The bytes are not a PDF."""


class EncryptedPdfError(Exception):
    """The PDF is password-protected and cannot be read."""


class UnreadablePdfError(Exception):
    """The PDF is malformed beyond recovery."""


class TooManyPagesError(Exception):
    """The PDF exceeds the page cap."""

    def __init__(self, max_pages: int) -> None:
        super().__init__(f"document exceeds the {max_pages} page limit")
        self.max_pages = max_pages


@dataclass(frozen=True)
class ExtractedPage:
    """One page's text layer. `text` is empty when the page carries no text."""

    page_number: int
    text: str

    @property
    def has_text(self) -> bool:
        return bool(self.text.strip())


@dataclass(frozen=True)
class ExtractionResult:
    pages: list[ExtractedPage]

    @property
    def needs_ocr(self) -> bool:
        """True when any page has no text layer, so the document is not fully read.

        Deliberately "any" rather than "all": a scanned exhibit stapled to a native
        PDF is exactly the case where a document-level "complete" would hide the one
        page nobody can read.
        """
        return any(not page.has_text for page in self.pages)


def extract_text_layer(
    data: bytes,
    *,
    max_pages: int = DEFAULT_MAX_PAGES,
    max_chars_per_page: int = DEFAULT_MAX_CHARS_PER_PAGE,
) -> ExtractionResult:
    """Read the embedded text of every page. Synchronous — call via `to_thread`."""
    if not data.startswith(PDF_MAGIC):
        raise NotAPdfError("bytes do not begin with a PDF header")

    try:
        reader = PdfReader(stream=BytesIO(data))
    except PyPdfError as exc:
        raise UnreadablePdfError(str(exc)) from exc

    if reader.is_encrypted:
        # Some PDFs are "encrypted" with an empty owner password and open fine; try
        # that before giving up, since court portals produce these routinely.
        try:
            opened = reader.decrypt("")
        except (PyPdfError, NotImplementedError) as exc:
            raise EncryptedPdfError("PDF is password-protected") from exc
        if not opened:
            raise EncryptedPdfError("PDF is password-protected")

    try:
        page_count = len(reader.pages)
    except PyPdfError as exc:
        raise UnreadablePdfError(str(exc)) from exc

    if page_count > max_pages:
        raise TooManyPagesError(max_pages)

    pages: list[ExtractedPage] = []
    for index in range(page_count):
        try:
            text = reader.pages[index].extract_text() or ""
        except (PyPdfError, ValueError, KeyError):
            # One unreadable page must not lose the other 400. An empty text layer
            # routes the page to OCR, which is the correct destination anyway.
            text = ""
        pages.append(ExtractedPage(page_number=index + 1, text=text[:max_chars_per_page]))

    if not pages:
        raise UnreadablePdfError("PDF contains no pages")

    return ExtractionResult(pages=pages)
