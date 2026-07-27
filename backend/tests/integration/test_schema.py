"""The schema's guarantees, proven against a real PostgreSQL.

The central one is the citation guarantee (ADR-0001 §2): an extracted fact must point
at the passage it came from. These tests exist to prove the database refuses the
alternative, so the rule cannot be bypassed by a future code path that forgets it.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Case,
    Document,
    DocumentKind,
    DocumentPage,
    ExtractedFact,
    FactField,
    IngestSource,
    Jurisdiction,
    Party,
    PartyRole,
    Passage,
    UserAccount,
)

SYNTHETIC_QUOTE = "Petitioner requests the Court enter an Order modifying timesharing."


async def _case_with_a_page(session: AsyncSession) -> tuple[Case, Document, DocumentPage]:
    """A minimal synthetic case file. No real case material (CLAUDE.md §3)."""
    owner = UserAccount(email=f"owner-{uuid.uuid4().hex[:8]}@example.test")
    session.add(owner)
    await session.flush()

    case = Case(owner_id=owner.id, title="Synthetic Matter", jurisdiction=Jurisdiction.florida)
    session.add(case)
    await session.flush()

    document = Document(
        case_id=case.id,
        title="Synthetic Motion",
        kind=DocumentKind.motion,
        ingest_source=IngestSource.upload,
        storage_key=f"synthetic/{uuid.uuid4().hex}",
        content_hash=uuid.uuid4().hex,
        page_count=1,
    )
    session.add(document)
    await session.flush()

    page = DocumentPage(document_id=document.id, page_number=1, text=SYNTHETIC_QUOTE)
    session.add(page)
    await session.flush()
    return case, document, page


async def test_a_fact_cannot_be_stored_without_the_passage_it_came_from(
    session: AsyncSession,
) -> None:
    """The citation guarantee. An unanchored fact must be unrepresentable."""
    _, document, _ = await _case_with_a_page(session)

    await session.execute(text("SAVEPOINT unanchored"))
    with pytest.raises((IntegrityError, DBAPIError)):
        await session.execute(
            text(
                "INSERT INTO extracted_fact "
                "(id, document_id, passage_id, field, value, extractor_version) "
                "VALUES (:id, :document_id, NULL, 'case_number', 'x', 'v1')"
            ),
            {"id": uuid.uuid4(), "document_id": document.id},
        )
    await session.rollback()


async def test_a_fact_stored_with_its_passage_round_trips(session: AsyncSession) -> None:
    _, document, page = await _case_with_a_page(session)
    passage = Passage(
        page_id=page.id, start_offset=0, end_offset=len(SYNTHETIC_QUOTE), quote=SYNTHETIC_QUOTE
    )
    session.add(passage)
    await session.flush()

    session.add(
        ExtractedFact(
            document_id=document.id,
            passage_id=passage.id,
            field=FactField.requested_relief,
            value="modification of timesharing",
            extractor_version="test-v1",
            confidence=0.82,
        )
    )
    await session.flush()

    stored = (
        await session.execute(select(ExtractedFact).where(ExtractedFact.document_id == document.id))
    ).scalar_one()
    assert stored.passage_id == passage.id
    assert stored.field is FactField.requested_relief


async def test_deleting_a_case_removes_every_fact_derived_from_it(
    session: AsyncSession,
) -> None:
    """Deletion must reach the whole graph — a fact surviving its case would be
    orphaned case material (CLAUDE.md §3)."""
    case, document, page = await _case_with_a_page(session)
    passage = Passage(page_id=page.id, start_offset=0, end_offset=5, quote="Peti")
    session.add(passage)
    await session.flush()
    session.add(
        ExtractedFact(
            document_id=document.id,
            passage_id=passage.id,
            field=FactField.case_number,
            value="00-0000-DR",
            extractor_version="test-v1",
        )
    )
    await session.flush()

    await session.execute(text('DELETE FROM "case" WHERE id = :id'), {"id": case.id})
    await session.flush()

    for table in ("document", "document_page", "passage", "extracted_fact"):
        remaining = (
            await session.execute(text(f"SELECT count(*) FROM {table}"))  # noqa: S608
        ).scalar_one()
        assert remaining == 0, f"{table} still holds rows after the case was deleted"


async def test_a_passage_cannot_end_before_it_starts(session: AsyncSession) -> None:
    _, _, page = await _case_with_a_page(session)
    session.add(Passage(page_id=page.id, start_offset=10, end_offset=4, quote="backwards"))
    with pytest.raises((IntegrityError, DBAPIError)):
        await session.flush()
    await session.rollback()


async def test_a_passage_cannot_start_before_the_page(session: AsyncSession) -> None:
    _, _, page = await _case_with_a_page(session)
    session.add(Passage(page_id=page.id, start_offset=-1, end_offset=4, quote="negative"))
    with pytest.raises((IntegrityError, DBAPIError)):
        await session.flush()
    await session.rollback()


async def test_confidence_outside_zero_to_one_is_rejected(session: AsyncSession) -> None:
    """A confidence above 1 would render as impossible certainty on the surface."""
    _, document, page = await _case_with_a_page(session)
    passage = Passage(page_id=page.id, start_offset=0, end_offset=4, quote="Peti")
    session.add(passage)
    await session.flush()

    session.add(
        ExtractedFact(
            document_id=document.id,
            passage_id=passage.id,
            field=FactField.court,
            value="Circuit Court",
            extractor_version="test-v1",
            confidence=1.5,
        )
    )
    with pytest.raises((IntegrityError, DBAPIError)):
        await session.flush()
    await session.rollback()


async def test_unmeasured_ocr_confidence_is_allowed_and_distinct_from_zero(
    session: AsyncSession,
) -> None:
    """NULL means "not measured" (a native PDF); 0.0 means "measured as unreadable".
    Collapsing the two would hide which pages were never checked."""
    _, document, _ = await _case_with_a_page(session)
    unmeasured = DocumentPage(
        document_id=document.id, page_number=2, text="native text", ocr_confidence=None
    )
    measured_zero = DocumentPage(
        document_id=document.id, page_number=3, text="", ocr_confidence=0.0
    )
    session.add_all([unmeasured, measured_zero])
    await session.flush()

    assert unmeasured.ocr_confidence is None
    assert measured_zero.ocr_confidence == 0.0


async def test_ocr_confidence_above_one_is_rejected(session: AsyncSession) -> None:
    _, document, _ = await _case_with_a_page(session)
    session.add(DocumentPage(document_id=document.id, page_number=4, ocr_confidence=1.2))
    with pytest.raises((IntegrityError, DBAPIError)):
        await session.flush()
    await session.rollback()


async def test_page_numbers_start_at_one(session: AsyncSession) -> None:
    _, document, _ = await _case_with_a_page(session)
    session.add(DocumentPage(document_id=document.id, page_number=0))
    with pytest.raises((IntegrityError, DBAPIError)):
        await session.flush()
    await session.rollback()


async def test_the_same_document_cannot_be_ingested_twice_into_one_case(
    session: AsyncSession,
) -> None:
    """The same order arrives from counsel and from the portal. That is one document."""
    case, document, _ = await _case_with_a_page(session)
    session.add(
        Document(
            case_id=case.id,
            title="Same bytes, different filename",
            kind=DocumentKind.order,
            ingest_source=IngestSource.email,
            storage_key=f"synthetic/{uuid.uuid4().hex}",
            content_hash=document.content_hash,
            page_count=1,
        )
    )
    with pytest.raises(IntegrityError):
        await session.flush()
    await session.rollback()


async def test_the_same_document_may_appear_in_two_different_cases(
    session: AsyncSession,
) -> None:
    """Parallel matters share exhibits; deduplication is scoped to a case, not global."""
    _, document, _ = await _case_with_a_page(session)
    other_owner = UserAccount(email=f"other-{uuid.uuid4().hex[:8]}@example.test")
    session.add(other_owner)
    await session.flush()
    other_case = Case(owner_id=other_owner.id, title="Parallel Matter")
    session.add(other_case)
    await session.flush()

    session.add(
        Document(
            case_id=other_case.id,
            title="Shared exhibit",
            kind=DocumentKind.exhibit,
            ingest_source=IngestSource.upload,
            storage_key=f"synthetic/{uuid.uuid4().hex}",
            content_hash=document.content_hash,
            page_count=1,
        )
    )
    await session.flush()


async def test_a_child_party_is_flagged_for_redaction(session: AsyncSession) -> None:
    """Minors are redacted from output by default, which needs a column to key off."""
    case, _, _ = await _case_with_a_page(session)
    child = Party(
        case_id=case.id, display_name="Synthetic Child", role=PartyRole.child, is_minor=True
    )
    session.add(child)
    await session.flush()

    stored = (await session.execute(select(Party).where(Party.case_id == case.id))).scalar_one()
    assert stored.is_minor is True
    assert stored.role is PartyRole.child


async def test_one_person_may_hold_two_roles_but_not_the_same_role_twice(
    session: AsyncSession,
) -> None:
    """A self-represented parent is both a party and their own counsel."""
    case, _, _ = await _case_with_a_page(session)
    session.add_all(
        [
            Party(case_id=case.id, display_name="Pat Doe", role=PartyRole.petitioner),
            Party(case_id=case.id, display_name="Pat Doe", role=PartyRole.counsel),
        ]
    )
    await session.flush()

    session.add(Party(case_id=case.id, display_name="Pat Doe", role=PartyRole.counsel))
    with pytest.raises(IntegrityError):
        await session.flush()
    await session.rollback()


async def test_a_case_defaults_to_the_florida_jurisdiction_profile(
    session: AsyncSession,
) -> None:
    owner = UserAccount(email=f"fl-{uuid.uuid4().hex[:8]}@example.test")
    session.add(owner)
    await session.flush()
    case = Case(owner_id=owner.id, title="Defaulted Matter")
    session.add(case)
    await session.flush()

    assert case.jurisdiction is Jurisdiction.florida


async def test_a_document_starts_unclassified_and_pending(session: AsyncSession) -> None:
    """Honest defaults: we have not read it yet, and we do not pretend otherwise."""
    case, _, _ = await _case_with_a_page(session)
    document = Document(
        case_id=case.id,
        title="Freshly uploaded",
        ingest_source=IngestSource.camera,
        storage_key=f"synthetic/{uuid.uuid4().hex}",
        content_hash=uuid.uuid4().hex,
    )
    session.add(document)
    await session.flush()

    assert document.kind is DocumentKind.unclassified
    assert document.ocr_status.value == "pending"
    assert document.page_count == 0


async def test_filing_dates_may_be_absent_rather_than_invented(session: AsyncSession) -> None:
    """Many documents state neither date. Inventing one would fabricate a fact."""
    case, _, _ = await _case_with_a_page(session)
    document = Document(
        case_id=case.id,
        title="Undated correspondence",
        kind=DocumentKind.correspondence,
        ingest_source=IngestSource.email,
        storage_key=f"synthetic/{uuid.uuid4().hex}",
        content_hash=uuid.uuid4().hex,
    )
    session.add(document)
    await session.flush()

    assert document.filed_at is None
    assert document.served_at is None


async def test_re_running_an_extractor_cannot_duplicate_the_same_fact(
    session: AsyncSession,
) -> None:
    _, document, page = await _case_with_a_page(session)
    passage = Passage(page_id=page.id, start_offset=0, end_offset=4, quote="Peti")
    session.add(passage)
    await session.flush()

    for _ in range(2):
        session.add(
            ExtractedFact(
                document_id=document.id,
                passage_id=passage.id,
                field=FactField.case_number,
                value="00-0000-DR",
                extractor_version="test-v1",
            )
        )
    with pytest.raises(IntegrityError):
        await session.flush()
    await session.rollback()


async def test_a_new_extractor_version_may_re_read_the_same_passage(
    session: AsyncSession,
) -> None:
    """Superseding a bad extraction run must not require deleting the old rows first."""
    _, document, page = await _case_with_a_page(session)
    passage = Passage(page_id=page.id, start_offset=0, end_offset=4, quote="Peti")
    session.add(passage)
    await session.flush()

    for version in ("test-v1", "test-v2"):
        session.add(
            ExtractedFact(
                document_id=document.id,
                passage_id=passage.id,
                field=FactField.case_number,
                value="00-0000-DR",
                extractor_version=version,
            )
        )
    await session.flush()

    count = (
        await session.execute(select(ExtractedFact).where(ExtractedFact.passage_id == passage.id))
    ).scalars()
    assert len(list(count)) == 2
