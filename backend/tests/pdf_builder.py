"""Builds minimal, valid PDFs for tests.

Hand-assembled rather than pulled from a generator library: the tests need a page with
a real text layer and a page with none in the same file, which is precisely the shape
that decides `needs_ocr`. Writing the bytes directly keeps that controllable and adds
no dependency.

Synthetic content only — no real case material ever enters a fixture (CLAUDE.md §3).
"""

from __future__ import annotations


def _escape(text: str) -> str:
    return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")


def make_pdf(page_texts: list[str | None]) -> bytes:
    """A PDF with one page per entry. `None` gives a page with no text layer.

    A page with no content stream is what a scanned filing looks like to a text
    extractor: the image is there, the words are not.
    """
    objects: list[bytes] = []

    def add(body: bytes) -> int:
        objects.append(body)
        return len(objects)

    # Reserve 1 for the catalog and 2 for the page tree so the numbering below is
    # stable regardless of how many pages there are.
    objects.append(b"")
    objects.append(b"")
    font_number = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    page_numbers: list[int] = []
    for text in page_texts:
        if text is None:
            page_number = add(
                b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << >> >>"
            )
        else:
            stream = f"BT /F1 12 Tf 72 720 Td ({_escape(text)}) Tj ET".encode("latin-1", "replace")
            contents_number = add(
                b"<< /Length "
                + str(len(stream)).encode()
                + b" >>\nstream\n"
                + stream
                + b"\nendstream"
            )
            page_number = add(
                b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                b"/Contents " + str(contents_number).encode() + b" 0 R "
                b"/Resources << /Font << /F1 " + str(font_number).encode() + b" 0 R >> >> >>"
            )
        page_numbers.append(page_number)

    kids = b" ".join(str(number).encode() + b" 0 R" for number in page_numbers)
    objects[0] = b"<< /Type /Catalog /Pages 2 0 R >>"
    objects[1] = (
        b"<< /Type /Pages /Kids [" + kids + b"] /Count " + str(len(page_numbers)).encode() + b" >>"
    )

    out = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for index, body in enumerate(objects, start=1):
        offsets.append(len(out))
        out += str(index).encode() + b" 0 obj\n" + body + b"\nendobj\n"

    xref_at = len(out)
    out += b"xref\n0 " + str(len(objects) + 1).encode() + b"\n"
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        b"trailer\n<< /Size " + str(len(objects) + 1).encode() + b" /Root 1 0 R >>\n"
        b"startxref\n" + str(xref_at).encode() + b"\n%%EOF\n"
    )
    return bytes(out)
