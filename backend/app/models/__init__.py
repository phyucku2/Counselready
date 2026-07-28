"""ORM models.

Imported here so `Base.metadata` is fully populated before Alembic autogenerate runs —
a model that is never imported is invisible to autogenerate and silently absent from
the migration.
"""

from __future__ import annotations

from app.models.audit import AuthEvent, AuthEventType
from app.models.case import Case, Jurisdiction, Party, PartyRole
from app.models.document import (
    Document,
    DocumentKind,
    DocumentPage,
    IngestSource,
    OcrStatus,
    Passage,
)
from app.models.event import CaseEvent, DatePrecision, EventKind, EventProvenance
from app.models.extraction import ExtractedFact, FactField
from app.models.session import UsedRefreshToken, UserSession
from app.models.user import UserAccount

__all__ = [
    "AuthEvent",
    "AuthEventType",
    "Case",
    "CaseEvent",
    "DatePrecision",
    "Document",
    "DocumentKind",
    "DocumentPage",
    "EventKind",
    "EventProvenance",
    "ExtractedFact",
    "FactField",
    "IngestSource",
    "Jurisdiction",
    "OcrStatus",
    "Party",
    "PartyRole",
    "Passage",
    "UsedRefreshToken",
    "UserAccount",
    "UserSession",
]
