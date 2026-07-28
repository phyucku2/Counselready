"""Case and document routes end to end.

The tests that matter most here are the isolation ones: one account must not be able
to see, touch, or confirm the existence of another's case file.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.main import app
from app.storage.local import LocalObjectStore
from tests.pdf_builder import make_pdf

PASSWORD = "correct-horse-battery-staple"
SECRET = "SYNTHETIC_SIGNING_KEY_LONG_ENOUGH_FOR_HS256"
LINE = "Petitioner requests modification of timesharing."


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


async def _case(client: AsyncClient, headers: dict[str, str], title: str = "My Matter") -> str:
    response = await client.post("/cases", json={"title": title}, headers=headers)
    assert response.status_code == 201, response.text
    case_id: str = response.json()["id"]
    return case_id


def _pdf(pages: list[str | None] | None = None) -> dict[str, tuple[str, bytes, str]]:
    return {"file": ("filing.pdf", make_pdf(pages or [LINE]), "application/pdf")}


async def test_creating_and_reading_a_case(client: AsyncClient) -> None:
    headers = await _signed_in(client)
    case_id = await _case(client, headers)

    response = await client.get(f"/cases/{case_id}", headers=headers)
    assert response.status_code == 200
    assert response.json()["title"] == "My Matter"
    assert response.json()["jurisdiction"] == "florida"


async def test_every_case_route_requires_authentication(client: AsyncClient) -> None:
    headers = await _signed_in(client)
    case_id = await _case(client, headers)

    assert (await client.get("/cases")).status_code == 401
    assert (await client.post("/cases", json={"title": "x"})).status_code == 401
    assert (await client.get(f"/cases/{case_id}")).status_code == 401
    assert (await client.get(f"/cases/{case_id}/documents")).status_code == 401
    assert (await client.post(f"/cases/{case_id}/documents", files=_pdf())).status_code == 401


async def test_listing_returns_only_your_own_cases(client: AsyncClient) -> None:
    mine = await _signed_in(client)
    theirs = await _signed_in(client)
    await _case(client, mine, title="Mine")
    await _case(client, theirs, title="Theirs")

    titles = [case["title"] for case in (await client.get("/cases", headers=mine)).json()]
    assert titles == ["Mine"]


async def test_another_accounts_case_is_a_404_not_a_403(client: AsyncClient) -> None:
    """A 403 would confirm the case exists. For a product holding one person's family
    court file, that is itself a disclosure."""
    mine = await _signed_in(client)
    theirs = await _signed_in(client)
    their_case = await _case(client, theirs)

    response = await client.get(f"/cases/{their_case}", headers=mine)
    assert response.status_code == 404
    # Identical to a case that never existed.
    absent = await client.get(f"/cases/{uuid.uuid4()}", headers=mine)
    assert absent.status_code == 404
    assert response.json() == absent.json()


async def test_documents_cannot_be_listed_from_another_accounts_case(
    client: AsyncClient,
) -> None:
    mine = await _signed_in(client)
    theirs = await _signed_in(client)
    their_case = await _case(client, theirs)

    assert (await client.get(f"/cases/{their_case}/documents", headers=mine)).status_code == 404


async def test_documents_cannot_be_uploaded_into_another_accounts_case(
    client: AsyncClient,
) -> None:
    mine = await _signed_in(client)
    theirs = await _signed_in(client)
    their_case = await _case(client, theirs)

    response = await client.post(f"/cases/{their_case}/documents", files=_pdf(), headers=mine)
    assert response.status_code == 404


async def test_uploading_a_pdf_creates_a_document_with_its_pages(
    client: AsyncClient,
) -> None:
    headers = await _signed_in(client)
    case_id = await _case(client, headers)

    response = await client.post(
        f"/cases/{case_id}/documents",
        files=_pdf([LINE, "Page two."]),
        data={"title": "Motion to Modify"},
        headers=headers,
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["title"] == "Motion to Modify"
    assert body["page_count"] == 2
    assert body["ocr_status"] == "complete"


async def test_a_scanned_pdf_is_reported_as_needing_ocr(client: AsyncClient) -> None:
    headers = await _signed_in(client)
    case_id = await _case(client, headers)

    response = await client.post(
        f"/cases/{case_id}/documents", files=_pdf([LINE, None]), headers=headers
    )
    assert response.json()["ocr_status"] == "needs_ocr"


async def test_the_filename_is_used_when_no_title_is_given(client: AsyncClient) -> None:
    headers = await _signed_in(client)
    case_id = await _case(client, headers)

    response = await client.post(f"/cases/{case_id}/documents", files=_pdf(), headers=headers)
    assert response.json()["title"] == "filing.pdf"


async def test_uploading_the_same_document_twice_names_the_existing_one(
    client: AsyncClient,
) -> None:
    headers = await _signed_in(client)
    case_id = await _case(client, headers)
    first = await client.post(f"/cases/{case_id}/documents", files=_pdf(), headers=headers)

    duplicate = await client.post(f"/cases/{case_id}/documents", files=_pdf(), headers=headers)
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"]["document_id"] == first.json()["id"]


async def test_a_non_pdf_upload_is_refused_with_a_plain_explanation(
    client: AsyncClient,
) -> None:
    headers = await _signed_in(client)
    case_id = await _case(client, headers)

    response = await client.post(
        f"/cases/{case_id}/documents",
        files={"file": ("notes.txt", b"just some text", "text/plain")},
        headers=headers,
    )
    assert response.status_code == 422
    assert "PDF" in response.json()["detail"]


async def test_an_empty_upload_is_refused(client: AsyncClient) -> None:
    headers = await _signed_in(client)
    case_id = await _case(client, headers)

    response = await client.post(
        f"/cases/{case_id}/documents",
        files={"file": ("empty.pdf", b"", "application/pdf")},
        headers=headers,
    )
    assert response.status_code == 422


async def test_an_oversized_upload_is_refused_with_413(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The cap is enforced on the real request path, not only in the reader's unit
    tests."""
    import app.api.cases as cases_module

    monkeypatch.setattr(cases_module, "DEFAULT_MAX_UPLOAD_BYTES", 512)
    headers = await _signed_in(client)
    case_id = await _case(client, headers)

    response = await client.post(
        f"/cases/{case_id}/documents",
        files={"file": ("big.pdf", make_pdf([LINE] * 40), "application/pdf")},
        headers=headers,
    )
    assert response.status_code == 413


async def test_documents_are_listed_for_their_own_case_only(client: AsyncClient) -> None:
    headers = await _signed_in(client)
    first_case = await _case(client, headers, title="First")
    second_case = await _case(client, headers, title="Second")

    await client.post(f"/cases/{first_case}/documents", files=_pdf(), headers=headers)

    assert len((await client.get(f"/cases/{first_case}/documents", headers=headers)).json()) == 1
    assert (await client.get(f"/cases/{second_case}/documents", headers=headers)).json() == []


async def test_case_access_is_audited_with_counts_not_content(
    client: AsyncClient, session: AsyncSession
) -> None:
    """CLAUDE.md §3: every read and write of case material is recorded, and the record
    holds counts and references only — never document text."""
    headers = await _signed_in(client)
    case_id = await _case(client, headers)
    await client.post(f"/cases/{case_id}/documents", files=_pdf(), headers=headers)
    await client.get(f"/cases/{case_id}", headers=headers)

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
    actions = [row[0] for row in rows]
    assert actions == ["case_created", "document_uploaded", "case_read"]
    assert all(LINE not in (row[1] or "") for row in rows)


async def test_a_refused_upload_into_another_case_is_not_audited_against_it(
    client: AsyncClient, session: AsyncSession
) -> None:
    """The ownership check runs before the handler, so a rejected attempt leaves no
    entry on the victim's case timeline."""
    mine = await _signed_in(client)
    theirs = await _signed_in(client)
    their_case = await _case(client, theirs)

    await client.post(f"/cases/{their_case}/documents", files=_pdf(), headers=mine)

    uploads = (
        await session.execute(
            text(
                "SELECT count(*) FROM case_audit_event "
                "WHERE case_id = :case_id AND action = 'document_uploaded'"
            ),
            {"case_id": uuid.UUID(their_case)},
        )
    ).scalar_one()
    assert uploads == 0
