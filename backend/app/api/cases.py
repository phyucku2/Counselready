"""Case and document routes.

Ownership is enforced by one dependency, `owned_case`, which every case-scoped route
depends on. Making it a dependency rather than a check inside each handler means
forgetting it requires actively omitting a parameter, not merely failing to remember a
line.

A case belonging to someone else returns **404, not 403**. A 403 confirms the case
exists, which for a product holding one person's family court file is a disclosure in
itself.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, DbSession
from app.core.config import settings
from app.ingest.limits import (
    DEFAULT_MAX_UPLOAD_BYTES,
    EmptyUploadError,
    UploadTooLargeError,
    read_bounded,
)
from app.ingest.pdf import (
    EncryptedPdfError,
    NotAPdfError,
    TooManyPagesError,
    UnreadablePdfError,
)
from app.ingest.service import DuplicateDocumentError, IngestRequest, ingest_document
from app.models.audit import CaseAction, CaseAuditEvent
from app.models.case import Case, Jurisdiction
from app.models.document import Document, DocumentKind, DocumentPage, IngestSource, Passage
from app.models.user import UserAccount
from app.storage.base import ObjectStore
from app.storage.local import LocalObjectStore

router = APIRouter(tags=["cases"])

CASE_NOT_FOUND = HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Case not found")

UPLOAD_CHUNK = 64 * 1024


def object_store(request: Request) -> ObjectStore:
    """The configured blob store.

    A local filesystem store until the Azure backend lands (ADR-0006); overridden in
    tests. Kept as a dependency so no handler reaches for a global.

    The root comes from configuration rather than a temporary directory: someone
    running this locally is putting real filings through it, and `/tmp` is both
    world-readable on a shared machine and cleared on reboot.
    """
    store = getattr(request.app.state, "object_store", None)
    if store is None:
        store = LocalObjectStore(Path(settings.object_root))
        request.app.state.object_store = store
    return store


async def owned_case(case_id: uuid.UUID, account: CurrentUser, session: DbSession) -> Case:
    """The case, if this account owns it. Otherwise a 404.

    Every case-scoped route depends on this, so an ownership check cannot be forgotten
    by omission — only by deliberately not asking for the case.
    """
    case = (
        await session.execute(select(Case).where(Case.id == case_id, Case.owner_id == account.id))
    ).scalar_one_or_none()
    if case is None:
        raise CASE_NOT_FOUND
    return case


OwnedCase = Annotated[Case, Depends(owned_case)]
Store = Annotated[ObjectStore, Depends(object_store)]

DOCUMENT_NOT_FOUND = HTTPException(
    status_code=status.HTTP_404_NOT_FOUND, detail="Document not found"
)


async def owned_document(document_id: uuid.UUID, case: OwnedCase, session: DbSession) -> Document:
    """The document, if it sits in a case this account owns. Otherwise a 404.

    Scoped through `owned_case` rather than looked up by id alone, so a document id
    guessed or copied from elsewhere cannot be read out of someone else's file.
    """
    document = (
        await session.execute(
            select(Document).where(Document.id == document_id, Document.case_id == case.id)
        )
    ).scalar_one_or_none()
    if document is None:
        raise DOCUMENT_NOT_FOUND
    return document


OwnedDocument = Annotated[Document, Depends(owned_document)]


def _audit(
    session: DbSession,
    *,
    account: UserAccount,
    case_id: uuid.UUID | None,
    action: CaseAction,
    detail: dict[str, int] | None = None,
) -> None:
    """Record access to case material. Counts and references only, never content."""
    session.add(
        CaseAuditEvent(actor_user_id=account.id, case_id=case_id, action=action, detail=detail)
    )


class CreateCaseRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    court: str | None = Field(default=None, max_length=200)
    case_number: str | None = Field(default=None, max_length=100)


class CaseResponse(BaseModel):
    id: str
    title: str
    jurisdiction: str
    court: str | None
    case_number: str | None


class DocumentResponse(BaseModel):
    id: str
    title: str
    kind: str
    page_count: int
    ocr_status: str
    filed_at: datetime | None


class PassageResponse(BaseModel):
    """A span the reader can be pointed at.

    Offsets *and* the stored quote travel together for the same reason the table keeps
    both: the surface highlights by offset, but if a page were ever re-extracted the
    quote is what proves the highlight still covers the words it claimed.
    """

    id: str
    start_offset: int
    end_offset: int
    quote: str


class PageResponse(BaseModel):
    page_number: int
    text: str
    # NULL means "not measured" — a native PDF with a text layer — which is not the
    # same as a measured zero, so it stays nullable all the way to the client.
    ocr_confidence: float | None
    passages: list[PassageResponse]


class DocumentDetailResponse(DocumentResponse):
    pages: list[PageResponse]


def _case_response(case: Case) -> CaseResponse:
    return CaseResponse(
        id=str(case.id),
        title=case.title,
        jurisdiction=case.jurisdiction.value,
        court=case.court,
        case_number=case.case_number,
    )


def _document_response(document: Document) -> DocumentResponse:
    return DocumentResponse(
        id=str(document.id),
        title=document.title,
        kind=document.kind.value,
        page_count=document.page_count,
        ocr_status=document.ocr_status.value,
        filed_at=document.filed_at,
    )


@router.post("/cases", response_model=CaseResponse, status_code=status.HTTP_201_CREATED)
async def create_case(
    body: CreateCaseRequest, account: CurrentUser, session: DbSession
) -> CaseResponse:
    case = Case(
        owner_id=account.id,
        title=body.title,
        jurisdiction=Jurisdiction.florida,
        court=body.court,
        case_number=body.case_number,
    )
    session.add(case)
    await session.flush()
    _audit(session, account=account, case_id=case.id, action=CaseAction.case_created)
    await session.flush()
    return _case_response(case)


@router.get("/cases", response_model=list[CaseResponse])
async def list_cases(account: CurrentUser, session: DbSession) -> list[CaseResponse]:
    cases = list(
        (
            await session.execute(
                select(Case).where(Case.owner_id == account.id).order_by(Case.created_at)
            )
        ).scalars()
    )
    _audit(
        session,
        account=account,
        case_id=None,
        action=CaseAction.case_list,
        detail={"cases": len(cases)},
    )
    await session.flush()
    return [_case_response(case) for case in cases]


@router.get("/cases/{case_id}", response_model=CaseResponse)
async def read_case(case: OwnedCase, account: CurrentUser, session: DbSession) -> CaseResponse:
    _audit(session, account=account, case_id=case.id, action=CaseAction.case_read)
    await session.flush()
    return _case_response(case)


@router.get("/cases/{case_id}/documents", response_model=list[DocumentResponse])
async def list_documents(
    case: OwnedCase, account: CurrentUser, session: DbSession
) -> list[DocumentResponse]:
    documents = list(
        (
            await session.execute(
                select(Document).where(Document.case_id == case.id).order_by(Document.created_at)
            )
        ).scalars()
    )
    _audit(
        session,
        account=account,
        case_id=case.id,
        action=CaseAction.document_list,
        detail={"documents": len(documents)},
    )
    await session.flush()
    return [_document_response(document) for document in documents]


@router.get(
    "/cases/{case_id}/documents/{document_id}",
    response_model=DocumentDetailResponse,
)
async def read_document(
    document: OwnedDocument, account: CurrentUser, session: DbSession
) -> DocumentDetailResponse:
    """The extracted text of one document, page by page, with its citable passages.

    This is the reader's view of their own filing, so nothing is redacted here. The
    redaction rule in CLAUDE.md §3 governs *generated output and exports* — material
    that leaves the account holder's hands. It was never meant to hide a person's own
    children's names from them while they read a document they already possess.
    """
    pages = list(
        (
            await session.execute(
                select(DocumentPage)
                .where(DocumentPage.document_id == document.id)
                .order_by(DocumentPage.page_number)
                .options(selectinload(DocumentPage.passages))
            )
        ).scalars()
    )
    _audit(
        session,
        account=account,
        case_id=document.case_id,
        action=CaseAction.document_read,
        detail={"pages": len(pages)},
    )
    await session.flush()

    return DocumentDetailResponse(
        **_document_response(document).model_dump(),
        pages=[
            PageResponse(
                page_number=page.page_number,
                text=page.text,
                ocr_confidence=page.ocr_confidence,
                # Sorted here rather than left to the relationship's arbitrary order:
                # a viewer highlighting spans in document order must not depend on
                # whatever sequence the database happened to return.
                passages=[
                    _passage_response(passage)
                    for passage in sorted(page.passages, key=lambda item: item.start_offset)
                ],
            )
            for page in pages
        ],
    )


def _passage_response(passage: Passage) -> PassageResponse:
    return PassageResponse(
        id=str(passage.id),
        start_offset=passage.start_offset,
        end_offset=passage.end_offset,
        quote=passage.quote,
    )


async def _stream(upload: UploadFile) -> AsyncIterator[bytes]:
    while chunk := await upload.read(UPLOAD_CHUNK):
        yield chunk


@router.post(
    "/cases/{case_id}/documents",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    request: Request,
    case: OwnedCase,
    account: CurrentUser,
    session: DbSession,
    store: Store,
    file: Annotated[UploadFile, File()],
    title: Annotated[str | None, Form()] = None,
    source: Annotated[str, Form()] = IngestSource.upload.value,
) -> DocumentResponse:
    """Ingest a document into a case.

    The body is read through the bounded reader (ADR-0006), so an oversized upload is
    refused while it is still arriving rather than after it is in memory.
    """
    declared = request.headers.get("content-length")
    try:
        data = await read_bounded(
            _stream(file),
            max_bytes=DEFAULT_MAX_UPLOAD_BYTES,
            declared_length=int(declared) if declared and declared.isdigit() else None,
        )
    except UploadTooLargeError as exc:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="That file is larger than the upload limit.",
        ) from exc
    except EmptyUploadError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="The file is empty."
        ) from exc

    try:
        ingest_source = IngestSource(source)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Unknown upload source."
        ) from exc

    try:
        document = await ingest_document(
            session,
            store,
            IngestRequest(
                case_id=case.id,
                title=title or (file.filename or "Untitled document"),
                ingest_source=ingest_source,
                data=data,
                kind=DocumentKind.unclassified,
            ),
        )
    except DuplicateDocumentError as exc:
        # Named rather than opaque: the same order arrives from counsel and the clerk
        # portal, so the useful answer is "you already have this", with its id.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "This document is already in the case.",
                "document_id": str(exc.existing_id),
            },
        ) from exc
    except NotAPdfError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="That file is not a PDF.",
        ) from exc
    except EncryptedPdfError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="That PDF is password-protected. Remove the password and try again.",
        ) from exc
    except TooManyPagesError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="That document has more pages than we can process.",
        ) from exc
    except UnreadablePdfError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="That PDF could not be read.",
        ) from exc

    _audit(
        session,
        account=account,
        case_id=case.id,
        action=CaseAction.document_uploaded,
        detail={"pages": document.page_count},
    )
    await session.flush()
    return _document_response(document)
