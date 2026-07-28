"""Document ingest.

Turns uploaded bytes into a `Document` and its `DocumentPage` rows.

Ordering is deliberate: the blob is written **before** the database row. If the
database write then fails, the result is an unreferenced object that a sweep can
collect — harmless. The reverse order would leave a `Document` row pointing at
storage that holds nothing, which is a broken record the user can see and no sweep can
repair.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingest.pdf import ExtractionResult, extract_text_layer
from app.models.document import Document, DocumentKind, DocumentPage, IngestSource, OcrStatus
from app.storage.base import ObjectStore, content_hash, storage_key


class DuplicateDocumentError(Exception):
    """These exact bytes are already in this case."""

    def __init__(self, existing_id: uuid.UUID) -> None:
        super().__init__("this document is already in the case")
        self.existing_id = existing_id


@dataclass(frozen=True)
class IngestRequest:
    case_id: uuid.UUID
    title: str
    ingest_source: IngestSource
    data: bytes
    kind: DocumentKind = DocumentKind.unclassified


async def ingest_document(
    session: AsyncSession, store: ObjectStore, request: IngestRequest
) -> Document:
    """Store the bytes, read what text they already carry, and persist the record."""
    digest = content_hash(request.data)

    existing = (
        await session.execute(
            select(Document.id).where(
                Document.case_id == request.case_id, Document.content_hash == digest
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        # The same order routinely arrives from counsel and from the clerk portal.
        # That is one document, and re-uploading it is not an error worth losing work
        # over — the caller is told which record it already is.
        raise DuplicateDocumentError(existing)

    key = storage_key(str(request.case_id), digest)
    await store.put(key, request.data)

    # CPU-bound parsing never runs on the event loop (CLAUDE.md §9).
    extraction: ExtractionResult = await asyncio.to_thread(extract_text_layer, request.data)

    document = Document(
        case_id=request.case_id,
        title=request.title,
        kind=request.kind,
        ingest_source=request.ingest_source,
        storage_key=key,
        content_hash=digest,
        page_count=len(extraction.pages),
        ocr_status=OcrStatus.needs_ocr if extraction.needs_ocr else OcrStatus.complete,
    )
    session.add(document)
    await session.flush()

    session.add_all(
        [
            DocumentPage(
                document_id=document.id,
                page_number=page.page_number,
                text=page.text,
                # NULL, not 0.0: an embedded text layer was read directly, so no
                # confidence was ever measured. OCR sets a real number later.
                ocr_confidence=None,
            )
            for page in extraction.pages
        ]
    )
    await session.flush()
    return document
