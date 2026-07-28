"""Timeline event guarantees, proven against a real PostgreSQL.

These tests exist because the rules they cover are the ones most likely to be
bypassed by a future code path in a hurry: attaching a user's typed note to a
document it did not come from, or presenting two parties' conflicting accounts as a
single settled fact.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Case,
    CaseEvent,
    DatePrecision,
    Document,
    DocumentKind,
    DocumentPage,
    EventKind,
    EventProvenance,
    IngestSource,
    Party,
    PartyRole,
    Passage,
    UserAccount,
)

MARCH = datetime(2026, 3, 3, 18, 0, tzinfo=UTC)
SYNTHETIC_TEXT = "Respondent did not return the children at the scheduled exchange."


class Fixture:
    """The pieces a timeline test needs, built synthetically (CLAUDE.md §3)."""

    def __init__(
        self,
        owner: UserAccount,
        case: Case,
        passage: Passage,
        petitioner: Party,
        respondent: Party,
    ) -> None:
        self.owner = owner
        self.case = case
        self.passage = passage
        self.petitioner = petitioner
        self.respondent = respondent


async def _fixture(session: AsyncSession) -> Fixture:
    owner = UserAccount(email=f"owner-{uuid.uuid4().hex[:8]}@example.test")
    session.add(owner)
    await session.flush()

    case = Case(owner_id=owner.id, title="Synthetic Matter")
    session.add(case)
    await session.flush()

    petitioner = Party(case_id=case.id, display_name="Pat Roe", role=PartyRole.petitioner)
    respondent = Party(case_id=case.id, display_name="Sam Roe", role=PartyRole.respondent)
    document = Document(
        case_id=case.id,
        title="Synthetic Motion",
        kind=DocumentKind.motion,
        ingest_source=IngestSource.upload,
        storage_key=f"synthetic/{uuid.uuid4().hex}",
        content_hash=uuid.uuid4().hex,
        page_count=1,
    )
    session.add_all([petitioner, respondent, document])
    await session.flush()

    page = DocumentPage(document_id=document.id, page_number=1, text=SYNTHETIC_TEXT)
    session.add(page)
    await session.flush()

    passage = Passage(
        page_id=page.id, start_offset=0, end_offset=len(SYNTHETIC_TEXT), quote=SYNTHETIC_TEXT
    )
    session.add(passage)
    await session.flush()
    return Fixture(owner, case, passage, petitioner, respondent)


async def test_a_documentary_event_must_cite_the_passage_it_came_from(
    session: AsyncSession,
) -> None:
    """The whole point of the provenance split: no unsupported documentary claims."""
    fixture = await _fixture(session)
    session.add(
        CaseEvent(
            case_id=fixture.case.id,
            kind=EventKind.alleged,
            provenance=EventProvenance.document_derived,
            passage_id=None,
            occurred_at=MARCH,
            summary="Claims an exchange was missed",
        )
    )
    with pytest.raises((IntegrityError, DBAPIError)):
        await session.flush()
    await session.rollback()


async def test_a_user_asserted_event_cannot_borrow_a_passage(session: AsyncSession) -> None:
    """A note the user typed must not be dressed up as something a filing said."""
    fixture = await _fixture(session)
    session.add(
        CaseEvent(
            case_id=fixture.case.id,
            kind=EventKind.alleged,
            provenance=EventProvenance.user_asserted,
            passage_id=fixture.passage.id,
            recorded_by_user_id=fixture.owner.id,
            occurred_at=MARCH,
            summary="I recorded that the exchange was missed",
        )
    )
    with pytest.raises((IntegrityError, DBAPIError)):
        await session.flush()
    await session.rollback()


async def test_a_user_asserted_event_must_name_its_author(session: AsyncSession) -> None:
    fixture = await _fixture(session)
    session.add(
        CaseEvent(
            case_id=fixture.case.id,
            kind=EventKind.alleged,
            provenance=EventProvenance.user_asserted,
            recorded_by_user_id=None,
            occurred_at=MARCH,
            summary="An anonymous assertion",
        )
    )
    with pytest.raises((IntegrityError, DBAPIError)):
        await session.flush()
    await session.rollback()


async def test_a_documentary_event_is_not_attributed_to_an_account_holder(
    session: AsyncSession,
) -> None:
    """A document said it; a person did not record it. Both columns cannot be set."""
    fixture = await _fixture(session)
    session.add(
        CaseEvent(
            case_id=fixture.case.id,
            kind=EventKind.alleged,
            provenance=EventProvenance.document_derived,
            passage_id=fixture.passage.id,
            recorded_by_user_id=fixture.owner.id,
            occurred_at=MARCH,
            summary="Both at once",
        )
    )
    with pytest.raises((IntegrityError, DBAPIError)):
        await session.flush()
    await session.rollback()


async def test_a_well_formed_documentary_event_stores_and_reaches_its_source(
    session: AsyncSession,
) -> None:
    fixture = await _fixture(session)
    event = CaseEvent(
        case_id=fixture.case.id,
        kind=EventKind.alleged,
        provenance=EventProvenance.document_derived,
        passage_id=fixture.passage.id,
        occurred_at=MARCH,
        date_precision=DatePrecision.day,
        summary="States the children were not returned at the scheduled exchange",
        asserted_by_party_id=fixture.petitioner.id,
        about_party_id=fixture.respondent.id,
    )
    session.add(event)
    await session.flush()

    stored = (await session.execute(select(CaseEvent).where(CaseEvent.id == event.id))).scalar_one()
    assert stored.passage_id == fixture.passage.id
    assert stored.recorded_by_user_id is None
    # The event can reach the exact words it came from, which is what the surface
    # needs in order to let a user check any statement it shows them.
    assert stored.passage is not None
    assert stored.passage.quote == SYNTHETIC_TEXT


async def test_a_well_formed_user_asserted_event_stores_without_a_passage(
    session: AsyncSession,
) -> None:
    fixture = await _fixture(session)
    event = CaseEvent(
        case_id=fixture.case.id,
        kind=EventKind.alleged,
        provenance=EventProvenance.user_asserted,
        recorded_by_user_id=fixture.owner.id,
        occurred_at=MARCH,
        summary="Recorded that the exchange did not happen",
        about_party_id=fixture.respondent.id,
    )
    session.add(event)
    await session.flush()

    stored = (await session.execute(select(CaseEvent).where(CaseEvent.id == event.id))).scalar_one()
    assert stored.passage_id is None
    assert stored.recorded_by_user_id == fixture.owner.id


async def test_two_parties_accounts_of_one_incident_remain_two_events(
    session: AsyncSession,
) -> None:
    """Conflicting accounts are never merged (CLAUDE.md §2). Each keeps its own
    citation and its own asserting party, so the surface can show both, attributed."""
    fixture = await _fixture(session)
    other_page = DocumentPage(
        document_id=(
            await session.execute(
                text("SELECT document_id FROM document_page WHERE id = :id"),
                {"id": fixture.passage.page_id},
            )
        ).scalar_one(),
        page_number=2,
        text="Respondent states the exchange occurred as scheduled.",
    )
    session.add(other_page)
    await session.flush()
    other_passage = Passage(
        page_id=other_page.id, start_offset=0, end_offset=20, quote="Respondent states the"
    )
    session.add(other_passage)
    await session.flush()

    session.add_all(
        [
            CaseEvent(
                case_id=fixture.case.id,
                kind=EventKind.alleged,
                provenance=EventProvenance.document_derived,
                passage_id=fixture.passage.id,
                occurred_at=MARCH,
                summary="States the children were not returned",
                asserted_by_party_id=fixture.petitioner.id,
            ),
            CaseEvent(
                case_id=fixture.case.id,
                kind=EventKind.alleged,
                provenance=EventProvenance.document_derived,
                passage_id=other_passage.id,
                occurred_at=MARCH,
                summary="States the exchange occurred as scheduled",
                asserted_by_party_id=fixture.respondent.id,
            ),
        ]
    )
    await session.flush()

    events = list(
        (
            await session.execute(select(CaseEvent).where(CaseEvent.case_id == fixture.case.id))
        ).scalars()
    )
    assert len(events) == 2
    assert {event.asserted_by_party_id for event in events} == {
        fixture.petitioner.id,
        fixture.respondent.id,
    }
    # Same moment, different accounts — the conflict is preserved, not resolved.
    assert {event.occurred_at for event in events} == {MARCH}


async def test_date_precision_defaults_to_day_and_records_coarser_sources(
    session: AsyncSession,
) -> None:
    """A filing that says only "in March" must not render as a precise timestamp."""
    fixture = await _fixture(session)
    vague = CaseEvent(
        case_id=fixture.case.id,
        kind=EventKind.alleged,
        provenance=EventProvenance.document_derived,
        passage_id=fixture.passage.id,
        occurred_at=datetime(2026, 3, 1, tzinfo=UTC),
        date_precision=DatePrecision.month,
        summary="States an incident occurred in March",
    )
    session.add(vague)
    await session.flush()
    assert vague.date_precision is DatePrecision.month

    defaulted = CaseEvent(
        case_id=fixture.case.id,
        kind=EventKind.procedural,
        provenance=EventProvenance.user_asserted,
        recorded_by_user_id=fixture.owner.id,
        occurred_at=MARCH,
        summary="Hearing attended",
    )
    session.add(defaulted)
    await session.flush()
    assert defaulted.date_precision is DatePrecision.day


async def test_removing_a_party_leaves_the_event_and_its_citation_intact(
    session: AsyncSession,
) -> None:
    """Losing an attribution must not silently delete the underlying record."""
    fixture = await _fixture(session)
    event = CaseEvent(
        case_id=fixture.case.id,
        kind=EventKind.alleged,
        provenance=EventProvenance.document_derived,
        passage_id=fixture.passage.id,
        occurred_at=MARCH,
        summary="States the children were not returned",
        asserted_by_party_id=fixture.petitioner.id,
    )
    session.add(event)
    await session.flush()

    await session.execute(text("DELETE FROM party WHERE id = :id"), {"id": fixture.petitioner.id})
    await session.flush()
    await session.refresh(event)

    assert event.asserted_by_party_id is None
    assert event.passage_id == fixture.passage.id


async def test_deleting_a_case_removes_its_timeline(session: AsyncSession) -> None:
    fixture = await _fixture(session)
    session.add(
        CaseEvent(
            case_id=fixture.case.id,
            kind=EventKind.procedural,
            provenance=EventProvenance.user_asserted,
            recorded_by_user_id=fixture.owner.id,
            occurred_at=MARCH,
            summary="Hearing attended",
        )
    )
    await session.flush()

    await session.execute(text('DELETE FROM "case" WHERE id = :id'), {"id": fixture.case.id})
    await session.flush()

    remaining = (await session.execute(text("SELECT count(*) FROM case_event"))).scalar_one()
    assert remaining == 0
