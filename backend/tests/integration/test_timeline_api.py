"""Timeline routes end to end.

The guarantees under test are the ones a chronology lives or dies by: what the account
holder typed is labelled as theirs, what a document says carries its citation, no
request body can turn the former into the latter, and a correction never overwrites
what was originally recorded.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.main import app
from app.models import (
    CaseEvent,
    DatePrecision,
    DocumentPage,
    EventKind,
    EventProvenance,
    Passage,
)
from app.storage.local import LocalObjectStore
from tests.pdf_builder import make_pdf

PASSWORD = "correct-horse-battery-staple"
SECRET = "SYNTHETIC_SIGNING_KEY_LONG_ENOUGH_FOR_HS256"
LINE = "Respondent did not return the children at the scheduled exchange."
MARCH = datetime(2026, 3, 3, 18, 0, tzinfo=UTC)


@pytest_asyncio.fixture()
async def client(session: AsyncSession, tmp_path: Path) -> AsyncIterator[AsyncClient]:
    async def _session_override() -> AsyncSession:
        return session

    app.dependency_overrides[get_session] = _session_override
    app.state.jwt_secret = SECRET
    app.state.object_store = LocalObjectStore(tmp_path / "objects")
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://testserver"
        ) as async_client:
            yield async_client
    finally:
        app.dependency_overrides.clear()


async def _signed_in(client: AsyncClient) -> dict[str, str]:
    email = f"user-{uuid.uuid4().hex[:10]}@example.com"
    await client.post("/auth/register", json={"email": email, "password": PASSWORD})
    tokens = (await client.post("/auth/login", json={"email": email, "password": PASSWORD})).json()
    return {"Authorization": f"Bearer {tokens['access_token']}"}


async def _case(client: AsyncClient, headers: dict[str, str]) -> str:
    case_id: str = (
        await client.post("/cases", json={"title": "My Matter"}, headers=headers)
    ).json()["id"]
    return case_id


def _entry(summary: str = "Exchange did not happen.", **overrides: object) -> dict[str, object]:
    return {"summary": summary, "occurred_at": MARCH.isoformat(), **overrides}


async def _added(client: AsyncClient, headers: dict[str, str], case_id: str) -> str:
    response = await client.post(f"/cases/{case_id}/events", json=_entry(), headers=headers)
    assert response.status_code == 201, response.text
    event_id: str = response.json()["id"]
    return event_id


async def _planted_documentary_event(
    client: AsyncClient, session: AsyncSession, headers: dict[str, str], case_id: str
) -> dict[str, str]:
    """A document-derived event, written directly.

    Extraction does not exist yet; the point of every test using this is that the read
    path resolves passage → page → document, not that anything populated it.
    """
    document = (
        await client.post(
            f"/cases/{case_id}/documents",
            files={"file": ("filing.pdf", make_pdf([LINE]), "application/pdf")},
            data={"title": "Motion to Modify"},
            headers=headers,
        )
    ).json()
    page = (
        await session.execute(
            select(DocumentPage).where(DocumentPage.document_id == uuid.UUID(document["id"]))
        )
    ).scalar_one()
    passage = Passage(page_id=page.id, start_offset=0, end_offset=len(LINE), quote=LINE)
    session.add(passage)
    await session.flush()
    event = CaseEvent(
        case_id=uuid.UUID(case_id),
        kind=EventKind.alleged,
        provenance=EventProvenance.document_derived,
        passage_id=passage.id,
        occurred_at=MARCH,
        date_precision=DatePrecision.day,
        summary="Petitioner states the exchange did not occur.",
    )
    session.add(event)
    await session.flush()
    return {"document_id": document["id"], "event_id": str(event.id)}


async def test_an_entry_is_recorded_as_the_account_holders_own_account(
    client: AsyncClient,
) -> None:
    headers = await _signed_in(client)
    case_id = await _case(client, headers)

    response = await client.post(f"/cases/{case_id}/events", json=_entry(), headers=headers)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["provenance"] == "user_asserted"
    # No citation, and the response says so rather than leaving the field off.
    assert body["citation"] is None
    assert body["notes"] == []


async def test_provenance_cannot_be_claimed_by_the_client(client: AsyncClient) -> None:
    """A request asserting documentary support must not get it. The CHECK constraint
    would catch a row like this; the API never lets one be built."""
    headers = await _signed_in(client)
    case_id = await _case(client, headers)

    response = await client.post(
        f"/cases/{case_id}/events",
        json=_entry(provenance="document_derived", passage_id=str(uuid.uuid4())),
        headers=headers,
    )
    assert response.status_code == 201
    assert response.json()["provenance"] == "user_asserted"
    assert response.json()["citation"] is None


async def test_an_entry_defaults_to_alleged_not_procedural(client: AsyncClient) -> None:
    """Something a person types about their own case is a claim, not a matter of
    record — the default must not quietly promote it."""
    headers = await _signed_in(client)
    case_id = await _case(client, headers)

    response = await client.post(f"/cases/{case_id}/events", json=_entry(), headers=headers)
    assert response.json()["kind"] == "alleged"


async def test_date_precision_survives_to_the_response(client: AsyncClient) -> None:
    """ "In March" must not come back as a timestamp the surface can render to the
    minute."""
    headers = await _signed_in(client)
    case_id = await _case(client, headers)

    response = await client.post(
        f"/cases/{case_id}/events", json=_entry(date_precision="month"), headers=headers
    )
    assert response.json()["date_precision"] == "month"


async def test_an_empty_summary_is_refused(client: AsyncClient) -> None:
    headers = await _signed_in(client)
    case_id = await _case(client, headers)

    response = await client.post(
        f"/cases/{case_id}/events", json=_entry(summary=""), headers=headers
    )
    assert response.status_code == 422


async def test_events_are_returned_in_chronological_order(client: AsyncClient) -> None:
    headers = await _signed_in(client)
    case_id = await _case(client, headers)
    for day, summary in ((9, "Third"), (1, "First"), (5, "Second")):
        await client.post(
            f"/cases/{case_id}/events",
            json={
                "summary": summary,
                "occurred_at": datetime(2026, 3, day, 12, 0, tzinfo=UTC).isoformat(),
            },
            headers=headers,
        )

    listed = (await client.get(f"/cases/{case_id}/events", headers=headers)).json()
    assert [event["summary"] for event in listed] == ["First", "Second", "Third"]


async def test_a_document_derived_event_carries_its_citation(
    client: AsyncClient, session: AsyncSession
) -> None:
    headers = await _signed_in(client)
    case_id = await _case(client, headers)
    planted = await _planted_documentary_event(client, session, headers, case_id)

    listed = (await client.get(f"/cases/{case_id}/events", headers=headers)).json()
    citation = listed[0]["citation"]
    assert citation["document_id"] == planted["document_id"]
    assert citation["document_title"] == "Motion to Modify"
    assert citation["page_number"] == 1
    assert citation["quote"] == LINE


async def test_the_timeline_of_another_account_is_a_404(client: AsyncClient) -> None:
    mine = await _signed_in(client)
    theirs = await _signed_in(client)
    their_case = await _case(client, theirs)

    assert (await client.get(f"/cases/{their_case}/events", headers=mine)).status_code == 404
    assert (
        await client.post(f"/cases/{their_case}/events", json=_entry(), headers=mine)
    ).status_code == 404


async def test_timeline_routes_require_authentication(client: AsyncClient) -> None:
    headers = await _signed_in(client)
    case_id = await _case(client, headers)
    event_id = await _added(client, headers, case_id)

    assert (await client.get(f"/cases/{case_id}/events")).status_code == 401
    assert (await client.post(f"/cases/{case_id}/events", json=_entry())).status_code == 401
    assert (
        await client.post(f"/cases/{case_id}/events/{event_id}/notes", json={"body": "x"})
    ).status_code == 401


# --- corrections -----------------------------------------------------------------


async def test_a_correction_leaves_the_entry_exactly_as_recorded(client: AsyncClient) -> None:
    """The whole point of the design: the note appears, the entry does not move."""
    headers = await _signed_in(client)
    case_id = await _case(client, headers)
    event_id = await _added(client, headers, case_id)
    before = (await client.get(f"/cases/{case_id}/events", headers=headers)).json()[0]

    response = await client.post(
        f"/cases/{case_id}/events/{event_id}/notes",
        json={"body": "This was the 5th, not the 3rd."},
        headers=headers,
    )
    assert response.status_code == 201, response.text

    after = (await client.get(f"/cases/{case_id}/events", headers=headers)).json()[0]
    assert after["summary"] == before["summary"]
    assert after["occurred_at"] == before["occurred_at"]
    assert after["date_precision"] == before["date_precision"]
    assert [note["body"] for note in after["notes"]] == ["This was the 5th, not the 3rd."]


async def test_corrections_accumulate_oldest_first(client: AsyncClient) -> None:
    headers = await _signed_in(client)
    case_id = await _case(client, headers)
    event_id = await _added(client, headers, case_id)
    for body in ("First correction.", "Second correction.", "Third correction."):
        await client.post(
            f"/cases/{case_id}/events/{event_id}/notes", json={"body": body}, headers=headers
        )

    notes = (await client.get(f"/cases/{case_id}/events", headers=headers)).json()[0]["notes"]
    assert [note["body"] for note in notes] == [
        "First correction.",
        "Second correction.",
        "Third correction.",
    ]


async def test_a_documentary_entry_can_be_corrected_without_losing_its_citation(
    client: AsyncClient, session: AsyncSession
) -> None:
    """The highest-value case. Contradicting a filing must not detach the filing: the
    citation still points at what the document actually says, and the disagreement is
    recorded as the account holder's, beside it."""
    headers = await _signed_in(client)
    case_id = await _case(client, headers)
    planted = await _planted_documentary_event(client, session, headers, case_id)

    await client.post(
        f"/cases/{case_id}/events/{planted['event_id']}/notes",
        json={"body": "The children were returned; I have the messages."},
        headers=headers,
    )

    event = (await client.get(f"/cases/{case_id}/events", headers=headers)).json()[0]
    assert event["provenance"] == "document_derived"
    assert event["summary"] == "Petitioner states the exchange did not occur."
    assert event["citation"]["quote"] == LINE
    assert event["notes"][0]["body"] == "The children were returned; I have the messages."


async def test_there_is_no_way_to_edit_or_delete_an_entry(client: AsyncClient) -> None:
    """Permanence is enforced by routes that do not exist, so the test has to assert
    an absence — and it asserts it against the schema, which fails the moment somebody
    adds one, rather than against a status code that would still pass if a PUT were
    added under a slightly different path."""
    mutating = {
        (path, method)
        for path, operations in app.openapi()["paths"].items()
        for method in operations
        if "/events/" in f"{path}/" and method in {"put", "patch", "delete"}
    }
    assert mutating == set()

    headers = await _signed_in(client)
    case_id = await _case(client, headers)
    event_id = await _added(client, headers, case_id)
    for attempt in (
        client.put(f"/cases/{case_id}/events/{event_id}", json=_entry(), headers=headers),
        client.patch(f"/cases/{case_id}/events/{event_id}", json=_entry(), headers=headers),
        client.delete(f"/cases/{case_id}/events/{event_id}", headers=headers),
    ):
        assert (await attempt).status_code == 404


async def test_an_empty_correction_is_refused(client: AsyncClient) -> None:
    headers = await _signed_in(client)
    case_id = await _case(client, headers)
    event_id = await _added(client, headers, case_id)

    response = await client.post(
        f"/cases/{case_id}/events/{event_id}/notes", json={"body": ""}, headers=headers
    )
    assert response.status_code == 422


async def test_an_entry_from_another_case_cannot_be_annotated(client: AsyncClient) -> None:
    """An event id is not a capability either — it must sit on the case in the path."""
    headers = await _signed_in(client)
    mine = await _case(client, headers)
    other = await _case(client, headers)
    event_id = await _added(client, headers, other)

    response = await client.post(
        f"/cases/{mine}/events/{event_id}/notes", json={"body": "x"}, headers=headers
    )
    assert response.status_code == 404


async def test_another_accounts_entry_cannot_be_annotated(client: AsyncClient) -> None:
    mine = await _signed_in(client)
    theirs = await _signed_in(client)
    their_case = await _case(client, theirs)
    their_event = await _added(client, theirs, their_case)

    response = await client.post(
        f"/cases/{their_case}/events/{their_event}/notes", json={"body": "x"}, headers=mine
    )
    assert response.status_code == 404


async def test_timeline_activity_is_audited_by_action_not_content(
    client: AsyncClient, session: AsyncSession
) -> None:
    headers = await _signed_in(client)
    case_id = await _case(client, headers)
    event_id = await _added(client, headers, case_id)
    await client.post(
        f"/cases/{case_id}/events/{event_id}/notes",
        json={"body": "This was the 5th, not the 3rd."},
        headers=headers,
    )
    await client.get(f"/cases/{case_id}/events", headers=headers)

    rows = list(
        (
            await session.execute(
                text(
                    "SELECT action, detail::text FROM case_audit_event "
                    "WHERE case_id = :case_id ORDER BY created_at"
                ),
                {"case_id": uuid.UUID(case_id)},
            )
        ).all()
    )
    assert [row[0] for row in rows] == [
        "case_created",
        "event_created",
        "event_note_created",
        "event_list",
    ]
    assert all("5th" not in (row[1] or "") for row in rows)
