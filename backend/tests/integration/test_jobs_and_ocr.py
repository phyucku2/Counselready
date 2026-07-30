"""Job queue and the OCR pipeline it drives."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.ingest.ocr import (
    ERROR_NO_DOCUMENT,
    ERROR_NO_ENGINE,
    OcrFailure,
    OcrPage,
    UnconfiguredEngine,
    run_ocr_for_document,
)
from app.ingest.service import IngestRequest, ingest_document
from app.jobs.models import MAX_ATTEMPTS, Job, JobKind, JobStatus
from app.jobs.queue import backoff_for, claim_next, enqueue, mark_failed, mark_succeeded
from app.models import Case, DocumentPage, IngestSource, OcrStatus, UserAccount
from app.storage.local import LocalObjectStore
from tests.pdf_builder import make_pdf

NOW = datetime(2026, 7, 28, 12, 0, tzinfo=UTC)
LINE = "Petitioner requests modification of timesharing."


class StubEngine:
    """Stands in for Azure Document Intelligence, which needs credentials the owner
    has not provisioned (ADR-0002)."""

    def __init__(self, pages: list[OcrPage]) -> None:
        self.pages = pages
        self.calls = 0

    async def read(self, data: bytes) -> list[OcrPage]:
        self.calls += 1
        return self.pages


class BrokenEngine:
    async def read(self, data: bytes) -> list[OcrPage]:
        raise RuntimeError("a message that must never reach the database")


@pytest.fixture()
def store(tmp_path: Path) -> LocalObjectStore:
    return LocalObjectStore(tmp_path / "objects")


async def _case(session: AsyncSession) -> Case:
    owner = UserAccount(email=f"owner-{uuid.uuid4().hex[:8]}@example.com")
    session.add(owner)
    await session.flush()
    case = Case(owner_id=owner.id, title="Synthetic Matter")
    session.add(case)
    await session.flush()
    return case


async def test_a_claimed_job_is_not_claimed_again(session: AsyncSession) -> None:
    """`FOR UPDATE SKIP LOCKED` is what lets several workers run without duplicating
    work."""
    await enqueue(
        session, kind=JobKind.ocr_document, payload={"document_id": str(uuid.uuid4())}, now=NOW
    )

    first = await claim_next(session, now=NOW)
    assert first is not None
    assert first.status is JobStatus.running
    assert first.attempts == 1

    assert await claim_next(session, now=NOW) is None


async def test_a_job_scheduled_for_later_is_not_claimed_yet(session: AsyncSession) -> None:
    job = await enqueue(
        session, kind=JobKind.ocr_document, payload={"document_id": str(uuid.uuid4())}, now=NOW
    )
    job.run_after = NOW + timedelta(minutes=5)
    await session.flush()

    assert await claim_next(session, now=NOW) is None
    assert await claim_next(session, now=NOW + timedelta(minutes=6)) is not None


async def test_a_failure_reschedules_with_backoff(session: AsyncSession) -> None:
    await enqueue(
        session, kind=JobKind.ocr_document, payload={"document_id": str(uuid.uuid4())}, now=NOW
    )
    job = await claim_next(session, now=NOW)
    assert job is not None

    await mark_failed(session, job, error="ocr_engine_failed", now=NOW)
    assert job.status is JobStatus.queued
    assert job.run_after > NOW
    # Not runnable immediately — a retry that fires at once just burns attempts.
    assert await claim_next(session, now=NOW) is None


async def test_a_job_gives_up_after_the_attempt_budget(session: AsyncSession) -> None:
    """A poison payload retried forever starves everything behind it."""
    await enqueue(
        session, kind=JobKind.ocr_document, payload={"document_id": str(uuid.uuid4())}, now=NOW
    )

    at = NOW
    for _ in range(MAX_ATTEMPTS):
        job = await claim_next(session, now=at)
        assert job is not None
        await mark_failed(session, job, error="ocr_engine_failed", now=at)
        at += timedelta(hours=1)

    final = (await session.execute(select(Job))).scalar_one()
    assert final.status is JobStatus.failed
    assert await claim_next(session, now=at) is None


async def test_backoff_grows_and_is_capped() -> None:
    assert backoff_for(1) < backoff_for(2) < backoff_for(3)
    assert backoff_for(50) == backoff_for(60)


async def test_a_succeeded_job_is_not_reclaimed(session: AsyncSession) -> None:
    await enqueue(
        session, kind=JobKind.ocr_document, payload={"document_id": str(uuid.uuid4())}, now=NOW
    )
    job = await claim_next(session, now=NOW)
    assert job is not None
    await mark_succeeded(session, job)

    assert await claim_next(session, now=NOW) is None


async def test_ingesting_a_scanned_document_enqueues_ocr(
    session: AsyncSession, store: LocalObjectStore
) -> None:
    """The job and the document commit together, so the queue can never hold work for
    a document that was rolled back."""
    case = await _case(session)
    await ingest_document(
        session,
        store,
        IngestRequest(
            case_id=case.id,
            title="Scanned",
            ingest_source=IngestSource.upload,
            data=make_pdf([LINE, None]),
        ),
    )

    job = (await session.execute(select(Job))).scalar_one()
    assert job.kind is JobKind.ocr_document


async def test_a_fully_native_document_enqueues_nothing(
    session: AsyncSession, store: LocalObjectStore
) -> None:
    case = await _case(session)
    await ingest_document(
        session,
        store,
        IngestRequest(
            case_id=case.id,
            title="Native",
            ingest_source=IngestSource.upload,
            data=make_pdf([LINE, "Page two."]),
        ),
    )
    assert (await session.execute(text("SELECT count(*) FROM job"))).scalar_one() == 0


async def test_ocr_fills_only_the_pages_without_a_text_layer(
    session: AsyncSession, store: LocalObjectStore
) -> None:
    """A native page's embedded text is more accurate than OCR, and re-reading it
    would degrade the citations pointing at it."""
    case = await _case(session)
    document = await ingest_document(
        session,
        store,
        IngestRequest(
            case_id=case.id,
            title="Mixed",
            ingest_source=IngestSource.upload,
            data=make_pdf([LINE, None]),
        ),
    )

    engine = StubEngine(
        [
            OcrPage(page_number=1, text="OCR SHOULD NOT OVERWRITE THIS", confidence=0.4),
            OcrPage(page_number=2, text="Recovered scanned text.", confidence=0.91),
        ]
    )
    filled = await run_ocr_for_document(
        session, document_id=document.id, store=store, engine=engine
    )
    assert filled == 1

    pages = list(
        (
            await session.execute(
                select(DocumentPage)
                .where(DocumentPage.document_id == document.id)
                .order_by(DocumentPage.page_number)
            )
        ).scalars()
    )
    assert LINE in pages[0].text
    assert pages[0].ocr_confidence is None  # never measured — still a text layer
    assert pages[1].text == "Recovered scanned text."
    assert pages[1].ocr_confidence == 0.91

    await session.refresh(document)
    assert document.ocr_status is OcrStatus.complete


async def test_a_page_ocr_cannot_read_leaves_the_document_needing_ocr(
    session: AsyncSession, store: LocalObjectStore
) -> None:
    """Marking it complete would claim we had read a page we had not."""
    case = await _case(session)
    document = await ingest_document(
        session,
        store,
        IngestRequest(
            case_id=case.id,
            title="Unreadable",
            ingest_source=IngestSource.upload,
            data=make_pdf([None, None]),
        ),
    )

    engine = StubEngine([OcrPage(page_number=1, text="Only the first page.", confidence=0.8)])
    await run_ocr_for_document(session, document_id=document.id, store=store, engine=engine)

    await session.refresh(document)
    assert document.ocr_status is OcrStatus.needs_ocr


async def test_the_default_engine_fails_loudly(
    session: AsyncSession, store: LocalObjectStore
) -> None:
    """A no-op engine reporting success would leave scanned pages empty while the
    surface claimed the document was read."""
    case = await _case(session)
    document = await ingest_document(
        session,
        store,
        IngestRequest(
            case_id=case.id,
            title="Scanned",
            ingest_source=IngestSource.upload,
            data=make_pdf([None]),
        ),
    )

    with pytest.raises(OcrFailure) as raised:
        await run_ocr_for_document(
            session, document_id=document.id, store=store, engine=UnconfiguredEngine()
        )
    assert raised.value.error_class == ERROR_NO_ENGINE


async def test_an_engine_error_never_leaks_its_message(
    session: AsyncSession, store: LocalObjectStore
) -> None:
    """Exception text can carry filenames and page content, so only a failure class is
    ever recorded (CLAUDE.md §3)."""
    case = await _case(session)
    document = await ingest_document(
        session,
        store,
        IngestRequest(
            case_id=case.id,
            title="Scanned",
            ingest_source=IngestSource.upload,
            data=make_pdf([None]),
        ),
    )

    with pytest.raises(OcrFailure) as raised:
        await run_ocr_for_document(
            session, document_id=document.id, store=store, engine=BrokenEngine()
        )
    assert "must never reach the database" not in str(raised.value)

    await enqueue(
        session, kind=JobKind.ocr_document, payload={"document_id": str(document.id)}, now=NOW
    )
    job = await claim_next(session, now=NOW)
    assert job is not None
    await mark_failed(session, job, error=raised.value.error_class, now=NOW)
    assert job.last_error == "ocr_engine_failed"


async def test_ocr_for_a_missing_document_is_a_classified_failure(
    session: AsyncSession, store: LocalObjectStore
) -> None:
    with pytest.raises(OcrFailure) as raised:
        await run_ocr_for_document(
            session,
            document_id=uuid.uuid4(),
            store=store,
            engine=StubEngine([]),
        )
    assert raised.value.error_class == ERROR_NO_DOCUMENT


async def test_the_job_payload_holds_identifiers_only(session: AsyncSession) -> None:
    """A queue row is not a place for case material."""
    document_id = uuid.uuid4()
    job = await enqueue(
        session, kind=JobKind.ocr_document, payload={"document_id": str(document_id)}, now=NOW
    )
    assert job.payload == {"document_id": str(document_id)}
    assert job.as_document_id() == document_id
