"""Document ingest against a real PostgreSQL and a real object store."""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingest.service import DuplicateDocumentError, IngestRequest, ingest_document
from app.models import Case, Document, DocumentKind, DocumentPage, IngestSource, UserAccount
from app.models.document import OcrStatus
from app.storage.base import ObjectNotFoundError, content_hash
from app.storage.local import LocalObjectStore
from tests.pdf_builder import make_pdf

SYNTHETIC_LINE = "Petitioner requests modification of timesharing."


@pytest.fixture()
def store(tmp_path: Path) -> LocalObjectStore:
    return LocalObjectStore(tmp_path / "objects")


async def _case(session: AsyncSession) -> Case:
    owner = UserAccount(email=f"owner-{uuid.uuid4().hex[:8]}@example.test")
    session.add(owner)
    await session.flush()
    case = Case(owner_id=owner.id, title="Synthetic Matter")
    session.add(case)
    await session.flush()
    return case


def _request(case: Case, pages: list[str | None], title: str = "Synthetic Motion") -> IngestRequest:
    return IngestRequest(
        case_id=case.id,
        title=title,
        ingest_source=IngestSource.upload,
        data=make_pdf(pages),
        kind=DocumentKind.motion,
    )


async def test_a_native_pdf_becomes_a_document_with_its_pages(
    session: AsyncSession, store: LocalObjectStore
) -> None:
    case = await _case(session)
    document = await ingest_document(session, store, _request(case, [SYNTHETIC_LINE, "Page two."]))

    assert document.page_count == 2
    assert document.ocr_status is OcrStatus.complete

    pages = list(
        (
            await session.execute(
                select(DocumentPage)
                .where(DocumentPage.document_id == document.id)
                .order_by(DocumentPage.page_number)
            )
        ).scalars()
    )
    assert [page.page_number for page in pages] == [1, 2]
    assert SYNTHETIC_LINE in pages[0].text
    # Read from an embedded text layer, so no confidence was ever measured.
    assert all(page.ocr_confidence is None for page in pages)


async def test_a_scanned_page_leaves_the_document_needing_ocr(
    session: AsyncSession, store: LocalObjectStore
) -> None:
    """`complete` would claim we had read a page we cannot read."""
    case = await _case(session)
    document = await ingest_document(session, store, _request(case, [SYNTHETIC_LINE, None]))

    assert document.ocr_status is OcrStatus.needs_ocr
    assert document.page_count == 2


async def test_the_bytes_are_stored_and_retrievable_under_the_recorded_key(
    session: AsyncSession, store: LocalObjectStore
) -> None:
    case = await _case(session)
    request = _request(case, [SYNTHETIC_LINE])
    document = await ingest_document(session, store, request)

    assert await store.get(document.storage_key) == request.data
    assert document.content_hash == content_hash(request.data)
    # Namespaced per case so destroying a case is a prefix operation, not a scan.
    assert document.storage_key.startswith(f"cases/{case.id}/")


async def test_re_uploading_identical_bytes_is_refused_and_names_the_existing_record(
    session: AsyncSession, store: LocalObjectStore
) -> None:
    """The same order arrives from counsel and the portal. That is one document, and
    the caller is told which one rather than left to guess."""
    case = await _case(session)
    request = _request(case, [SYNTHETIC_LINE])
    first = await ingest_document(session, store, request)

    with pytest.raises(DuplicateDocumentError) as raised:
        await ingest_document(session, store, _request(case, [SYNTHETIC_LINE], title="Renamed"))

    assert raised.value.existing_id == first.id
    assert (
        len(
            list(
                (
                    await session.execute(select(Document).where(Document.case_id == case.id))
                ).scalars()
            )
        )
        == 1
    )


async def test_the_same_document_may_be_ingested_into_a_second_case(
    session: AsyncSession, store: LocalObjectStore
) -> None:
    """Parallel matters share exhibits; deduplication is per case, not global."""
    first_case = await _case(session)
    second_case = await _case(session)
    await ingest_document(session, store, _request(first_case, [SYNTHETIC_LINE]))
    second = await ingest_document(session, store, _request(second_case, [SYNTHETIC_LINE]))

    assert second.case_id == second_case.id


async def test_a_failed_database_write_leaves_no_record_pointing_at_missing_bytes(
    session: AsyncSession, store: LocalObjectStore
) -> None:
    """Ordering check. The blob is written first, so a database failure leaves an
    unreferenced object a sweep can collect — never a document row whose bytes are
    absent, which is a broken record no sweep can repair."""
    case = await _case(session)
    request = _request(case, [SYNTHETIC_LINE])
    document = await ingest_document(session, store, request)
    key = document.storage_key

    await session.rollback()

    # The row is gone with the transaction; the object survives and is collectable.
    survivors = list(
        (await session.execute(select(Document).where(Document.case_id == case.id))).scalars()
    )
    assert survivors == []
    assert await store.get(key) == request.data


async def test_a_missing_object_raises_rather_than_returning_empty_bytes(
    store: LocalObjectStore,
) -> None:
    with pytest.raises(ObjectNotFoundError):
        await store.get("cases/none/documents/missing")


async def test_deleting_an_absent_object_is_not_an_error(store: LocalObjectStore) -> None:
    await store.delete("cases/none/documents/missing")


async def test_storing_identical_content_twice_is_idempotent(store: LocalObjectStore) -> None:
    """Content-addressed keys are what make blob-before-row safe to retry."""
    await store.put("cases/x/documents/abc", b"payload")
    await store.put("cases/x/documents/abc", b"payload")
    assert await store.get("cases/x/documents/abc") == b"payload"


async def test_a_key_escaping_the_store_root_is_refused(store: LocalObjectStore) -> None:
    with pytest.raises(ValueError, match="escapes the store root"):
        await store.put("../../etc/passwd", b"nope")
