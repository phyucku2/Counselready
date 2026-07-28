"""OCR seam and the job that drives it.

The engine is a protocol, not a choice made here. ADR-0002 puts inference inside the
Azure tenant, and Azure Document Intelligence needs a subscription the owner has not
provisioned — so the pipeline is built and tested against the seam, and the concrete
engine lands when credentials exist. This is the same pattern as `ObjectStore`.

What OCR writes is a per-page **measured** confidence, which is why the schema
distinguishes NULL ("never measured", a native text layer) from a real number
(ADR-0004). A page that OCR could not read gets a low confidence, not a null.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document, DocumentPage, OcrStatus
from app.storage.base import ObjectStore


@dataclass(frozen=True)
class OcrPage:
    page_number: int
    text: str
    confidence: float


class OcrEngine(Protocol):
    """Reads text from document bytes. Implementations run off the event loop."""

    async def read(self, data: bytes) -> list[OcrPage]:
        """Text and a measured confidence for every page."""
        ...


class OcrUnavailableError(RuntimeError):
    """No OCR engine is configured."""


class UnconfiguredEngine:
    """The default. Fails loudly rather than silently marking documents complete.

    A no-op engine that reported success would leave scanned pages permanently empty
    while the surface claimed the document had been read — the exact dishonesty the
    `needs_ocr` state exists to prevent.
    """

    async def read(self, data: bytes) -> list[OcrPage]:
        raise OcrUnavailableError("no OCR engine is configured")


# Failure classes. A closed vocabulary, because the alternative is an exception message
# in the database, and those carry filenames and page text.
ERROR_NO_ENGINE = "ocr_engine_unavailable"
ERROR_MISSING_OBJECT = "document_bytes_missing"
ERROR_ENGINE_FAILED = "ocr_engine_failed"
ERROR_NO_DOCUMENT = "document_not_found"


class OcrFailure(Exception):
    """Carries a failure class, never a message from the underlying error."""

    def __init__(self, error_class: str) -> None:
        super().__init__(error_class)
        self.error_class = error_class


async def run_ocr_for_document(
    session: AsyncSession,
    *,
    document_id: uuid.UUID,
    store: ObjectStore,
    engine: OcrEngine,
) -> int:
    """OCR one document's unread pages. Returns how many pages were filled in.

    Only pages without a text layer are sent: a native PDF's embedded text is more
    accurate than anything OCR would produce, so re-reading it would degrade the
    citations that point at it.
    """
    document = (
        await session.execute(select(Document).where(Document.id == document_id))
    ).scalar_one_or_none()
    if document is None:
        raise OcrFailure(ERROR_NO_DOCUMENT)

    document.ocr_status = OcrStatus.processing
    await session.flush()

    try:
        data = await store.get(document.storage_key)
    except Exception as exc:
        raise OcrFailure(ERROR_MISSING_OBJECT) from exc

    try:
        pages = await engine.read(data)
    except OcrUnavailableError as exc:
        raise OcrFailure(ERROR_NO_ENGINE) from exc
    except Exception as exc:
        raise OcrFailure(ERROR_ENGINE_FAILED) from exc

    by_number = {page.page_number: page for page in pages}
    stored_pages = list(
        (
            await session.execute(
                select(DocumentPage).where(DocumentPage.document_id == document.id)
            )
        ).scalars()
    )

    filled = 0
    for stored in stored_pages:
        if stored.text.strip():
            continue
        result = by_number.get(stored.page_number)
        if result is None:
            continue
        stored.text = result.text
        stored.ocr_confidence = result.confidence
        filled += 1

    # Complete only when every page now has text. A page OCR could not read leaves the
    # document honestly marked as still needing it.
    document.ocr_status = (
        OcrStatus.complete
        if all(page.text.strip() for page in stored_pages)
        else OcrStatus.needs_ocr
    )
    await session.flush()
    return filled
