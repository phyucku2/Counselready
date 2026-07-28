"""PDF text-layer extraction."""

from __future__ import annotations

import pytest

from app.ingest.pdf import (
    EncryptedPdfError,
    NotAPdfError,
    TooManyPagesError,
    UnreadablePdfError,
    extract_text_layer,
)
from tests.pdf_builder import make_pdf

SYNTHETIC_LINE = "Petitioner requests modification of timesharing."


def test_text_is_read_from_pages_that_carry_it() -> None:
    result = extract_text_layer(make_pdf([SYNTHETIC_LINE]))
    assert len(result.pages) == 1
    assert SYNTHETIC_LINE in result.pages[0].text
    assert result.needs_ocr is False


def test_a_page_with_no_text_layer_marks_the_document_as_needing_ocr() -> None:
    """A scanned filing has an image and no words. Reporting it as read would be a lie."""
    result = extract_text_layer(make_pdf([None]))
    assert result.pages[0].text == ""
    assert result.needs_ocr is True


def test_one_scanned_page_among_native_ones_still_needs_ocr() -> None:
    """The case that a document-level average would hide."""
    result = extract_text_layer(make_pdf([SYNTHETIC_LINE, None, "Third page."]))
    assert [page.has_text for page in result.pages] == [True, False, True]
    assert result.needs_ocr is True


def test_page_numbers_are_one_based_and_sequential() -> None:
    """They become citations, so they must match what a person sees on the page."""
    result = extract_text_layer(make_pdf(["one", "two", "three"]))
    assert [page.page_number for page in result.pages] == [1, 2, 3]


def test_bytes_that_are_not_a_pdf_are_rejected() -> None:
    with pytest.raises(NotAPdfError):
        extract_text_layer(b"This is a plain text file, not a PDF.")


def test_a_pdf_header_with_garbage_after_it_is_rejected_cleanly() -> None:
    """Right magic, wrong everything else — must raise, not crash."""
    with pytest.raises((UnreadablePdfError, EncryptedPdfError)):
        extract_text_layer(b"%PDF-1.4\nnot actually a pdf body")


def test_an_empty_payload_is_rejected() -> None:
    with pytest.raises(NotAPdfError):
        extract_text_layer(b"")


def test_a_document_over_the_page_cap_is_rejected() -> None:
    with pytest.raises(TooManyPagesError):
        extract_text_layer(make_pdf(["page"] * 5), max_pages=4)


def test_a_document_at_the_page_cap_is_accepted() -> None:
    assert len(extract_text_layer(make_pdf(["page"] * 4), max_pages=4).pages) == 4


def test_per_page_text_is_truncated_at_the_character_cap() -> None:
    """Bounds a pathological page; the cap is applied per page, not per document."""
    result = extract_text_layer(make_pdf(["A" * 500]), max_chars_per_page=100)
    assert len(result.pages[0].text) == 100


def test_an_encrypted_pdf_is_reported_as_encrypted_not_as_empty() -> None:
    """Silently returning zero pages would send it to OCR and quietly produce nothing."""
    from io import BytesIO

    from pypdf import PdfWriter

    writer = PdfWriter(clone_from=BytesIO(make_pdf([SYNTHETIC_LINE])))
    writer.encrypt("SYNTHETIC_PASSWORD")
    buffer = BytesIO()
    writer.write(buffer)

    with pytest.raises(EncryptedPdfError):
        extract_text_layer(buffer.getvalue())
