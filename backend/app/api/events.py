"""Timeline routes.

Only **user_asserted** events can be created through the API. Document-derived events
are written by extraction, which is the only code that holds a passage to cite, and
routing them through a request body would let a client claim documentary support for
something no document says — precisely what the CHECK constraints on `case_event`
exist to prevent (ADR-0005). The constraint would catch it; the API should never get
that far.

Entries are **permanent**: there is no update and no delete. A correction is a note
recorded beside the entry (`POST .../events/{id}/notes`), which is why the read shape
carries `notes` on every event rather than treating them as a detail view.

Reading returns both provenances, merged into one chronology, each carrying where it
came from so the surface can say so.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.cases import OwnedCase, _audit
from app.api.deps import CurrentUser, DbSession
from app.models.audit import CaseAction
from app.models.document import DocumentPage, Passage
from app.models.event import (
    CaseEvent,
    CaseEventNote,
    DatePrecision,
    EventKind,
    EventProvenance,
)

router = APIRouter(tags=["timeline"])

EVENT_NOT_FOUND = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Entry not found")


class CreateEventRequest(BaseModel):
    """What a person can record themselves.

    `provenance` is deliberately absent: it is not the client's to choose. Everything
    entered here is the account holder's own account of events, and is stored and
    labelled as such.
    """

    summary: str = Field(min_length=1, max_length=2000)
    occurred_at: datetime
    kind: EventKind = EventKind.alleged
    date_precision: DatePrecision = DatePrecision.day


class CreateNoteRequest(BaseModel):
    body: str = Field(min_length=1, max_length=2000)


class NoteResponse(BaseModel):
    id: str
    body: str
    created_at: datetime


class CitationResponse(BaseModel):
    """Where a document-derived event came from, precise enough to go and look."""

    document_id: str
    document_title: str
    page_number: int
    quote: str


class EventResponse(BaseModel):
    id: str
    kind: str
    provenance: str
    occurred_at: datetime
    date_precision: str
    summary: str
    # Present exactly when provenance is document_derived — the response shape mirrors
    # the constraint, so a client cannot render an uncited event as though sourced.
    citation: CitationResponse | None
    # Corrections and clarifications, oldest first. Always the account holder's own
    # words, never documentary, whatever the event they hang off.
    notes: list[NoteResponse]


def _citation(event: CaseEvent) -> CitationResponse | None:
    passage = event.passage
    if passage is None:
        return None
    page = passage.page
    return CitationResponse(
        document_id=str(page.document_id),
        document_title=page.document.title,
        page_number=page.page_number,
        quote=passage.quote,
    )


def _note_response(note: CaseEventNote) -> NoteResponse:
    return NoteResponse(id=str(note.id), body=note.body, created_at=note.created_at)


def _event_response(event: CaseEvent) -> EventResponse:
    return EventResponse(
        id=str(event.id),
        kind=event.kind.value,
        provenance=event.provenance.value,
        occurred_at=event.occurred_at,
        date_precision=event.date_precision.value,
        summary=event.summary,
        citation=_citation(event),
        notes=[_note_response(note) for note in event.notes],
    )


async def owned_event(event_id: uuid.UUID, case: OwnedCase, session: DbSession) -> CaseEvent:
    """The event, if it sits on a case this account owns. Otherwise a 404.

    Scoped through `owned_case` and then filtered by `case_id`, matching the document
    routes: an id from elsewhere is not a capability.
    """
    event = (
        await session.execute(
            select(CaseEvent).where(CaseEvent.id == event_id, CaseEvent.case_id == case.id)
        )
    ).scalar_one_or_none()
    if event is None:
        raise EVENT_NOT_FOUND
    return event


OwnedEvent = Annotated[CaseEvent, Depends(owned_event)]


@router.get("/cases/{case_id}/events", response_model=list[EventResponse])
async def list_events(
    case: OwnedCase, account: CurrentUser, session: DbSession
) -> list[EventResponse]:
    events = list(
        (
            await session.execute(
                select(CaseEvent)
                .where(CaseEvent.case_id == case.id)
                # created_at breaks ties so a chronology with two things on the same
                # day renders in a stable order rather than shuffling between loads.
                .order_by(CaseEvent.occurred_at, CaseEvent.created_at)
                .options(
                    selectinload(CaseEvent.passage)
                    .selectinload(Passage.page)
                    .selectinload(DocumentPage.document),
                    selectinload(CaseEvent.notes),
                )
            )
        ).scalars()
    )
    _audit(
        session,
        account=account,
        case_id=case.id,
        action=CaseAction.event_list,
        detail={"events": len(events)},
    )
    await session.flush()
    return [_event_response(event) for event in events]


@router.post(
    "/cases/{case_id}/events", response_model=EventResponse, status_code=status.HTTP_201_CREATED
)
async def create_event(
    body: CreateEventRequest, case: OwnedCase, account: CurrentUser, session: DbSession
) -> EventResponse:
    event = CaseEvent(
        case_id=case.id,
        kind=body.kind,
        provenance=EventProvenance.user_asserted,
        recorded_by_user_id=account.id,
        occurred_at=body.occurred_at,
        date_precision=body.date_precision,
        summary=body.summary,
    )
    session.add(event)
    await session.flush()
    _audit(session, account=account, case_id=case.id, action=CaseAction.event_created)
    await session.flush()
    # Built without touching `event.passage` or `event.notes`: a freshly created
    # user-asserted event has neither, and reaching for a relationship would emit a
    # lazy load from async context for a value already known to be empty.
    return EventResponse(
        id=str(event.id),
        kind=event.kind.value,
        provenance=event.provenance.value,
        occurred_at=event.occurred_at,
        date_precision=event.date_precision.value,
        summary=event.summary,
        citation=None,
        notes=[],
    )


@router.post(
    "/cases/{case_id}/events/{event_id}/notes",
    response_model=NoteResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_note(
    body: CreateNoteRequest,
    event: OwnedEvent,
    case: OwnedCase,
    account: CurrentUser,
    session: DbSession,
) -> NoteResponse:
    """Record a correction beside an entry.

    Deliberately additive. The entry it hangs off is never touched — not its summary,
    not its date, and for a document-derived entry not its citation, which still
    points at what the filing actually says. A reader sees both, in that order.
    """
    note = CaseEventNote(event_id=event.id, author_user_id=account.id, body=body.body)
    session.add(note)
    await session.flush()
    _audit(session, account=account, case_id=case.id, action=CaseAction.event_note_created)
    await session.flush()
    return _note_response(note)
