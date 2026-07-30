"""ORM models.

Imported here so `Base.metadata` is fully populated before Alembic autogenerate runs —
a model that is never imported is invisible to autogenerate and silently absent from
the migration.
"""

from __future__ import annotations

from app.jobs.models import Job, JobKind, JobStatus
from app.models.audit import AuthEvent, AuthEventType, CaseAction, CaseAuditEvent
from app.models.case import Case, Jurisdiction, Party, PartyRole
from app.models.document import (
    Document,
    DocumentKind,
    DocumentPage,
    IngestSource,
    OcrStatus,
    Passage,
)
from app.models.event import (
    CaseEvent,
    CaseEventNote,
    DatePrecision,
    EventKind,
    EventProvenance,
)
from app.models.extraction import ExtractedFact, FactField
from app.models.mfa import RecoveryCode, UserMfa
from app.models.passkey import Passkey, PasskeyChallenge
from app.models.session import UsedRefreshToken, UserSession
from app.models.user import UserAccount

__all__ = [
    "AuthEvent",
    "AuthEventType",
    "Case",
    "CaseAction",
    "CaseAuditEvent",
    "CaseEvent",
    "CaseEventNote",
    "DatePrecision",
    "Document",
    "DocumentKind",
    "DocumentPage",
    "EventKind",
    "EventProvenance",
    "ExtractedFact",
    "FactField",
    "IngestSource",
    "Job",
    "JobKind",
    "JobStatus",
    "Jurisdiction",
    "OcrStatus",
    "Party",
    "PartyRole",
    "Passage",
    "Passkey",
    "PasskeyChallenge",
    "RecoveryCode",
    "UsedRefreshToken",
    "UserAccount",
    "UserMfa",
    "UserSession",
]
