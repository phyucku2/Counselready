"""timeline events with provenance

Adds `case_event`, whose two CHECK constraints encode the rule that an event may not
claim documentary support it does not have: document-derived events must cite a
passage and must not be attributed to a person, and user-asserted events must name
their author and must not carry a passage.

Enum types are created and dropped explicitly — see the note in the initial migration.

Revision ID: 8a1be962755b
Revises: 2d61942264a6
Create Date: 2026-07-28 00:04:11.000000+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "8a1be962755b"
down_revision: str | None = "2d61942264a6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

event_kind = postgresql.ENUM("procedural", "alleged", name="event_kind", create_type=False)

event_provenance = postgresql.ENUM(
    "document_derived", "user_asserted", name="event_provenance", create_type=False
)

date_precision = postgresql.ENUM(
    "exact", "day", "month", "year", name="date_precision", create_type=False
)

ALL_ENUMS = (event_kind, event_provenance, date_precision)

CITES_A_PASSAGE = (
    "(provenance = 'document_derived' AND passage_id IS NOT NULL)"
    " OR (provenance = 'user_asserted' AND passage_id IS NULL)"
)

NAMES_ITS_AUTHOR = (
    "(provenance = 'user_asserted' AND recorded_by_user_id IS NOT NULL)"
    " OR (provenance = 'document_derived' AND recorded_by_user_id IS NULL)"
)


def upgrade() -> None:
    bind = op.get_bind()
    for enum in ALL_ENUMS:
        enum.create(bind, checkfirst=True)

    op.create_table(
        "case_event",
        sa.Column("case_id", sa.UUID(), nullable=False),
        sa.Column("kind", event_kind, nullable=False),
        sa.Column("provenance", event_provenance, nullable=False),
        sa.Column("passage_id", sa.UUID(), nullable=True),
        sa.Column("recorded_by_user_id", sa.UUID(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("date_precision", date_precision, nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("asserted_by_party_id", sa.UUID(), nullable=True),
        sa.Column("about_party_id", sa.UUID(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            CITES_A_PASSAGE, name=op.f("ck_case_event_documentary_events_cite_a_passage")
        ),
        sa.CheckConstraint(
            NAMES_ITS_AUTHOR, name=op.f("ck_case_event_asserted_events_name_their_author")
        ),
        sa.ForeignKeyConstraint(
            ["about_party_id"],
            ["party.id"],
            name=op.f("fk_case_event_about_party_id_party"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["asserted_by_party_id"],
            ["party.id"],
            name=op.f("fk_case_event_asserted_by_party_id_party"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["case_id"], ["case.id"], name=op.f("fk_case_event_case_id_case"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["passage_id"],
            ["passage.id"],
            name=op.f("fk_case_event_passage_id_passage"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["recorded_by_user_id"],
            ["user_account.id"],
            name=op.f("fk_case_event_recorded_by_user_id_user_account"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_case_event")),
    )
    op.create_index(op.f("ix_case_event_case_id"), "case_event", ["case_id"], unique=False)
    # The timeline's read pattern: one case, ordered by when things happened.
    op.create_index(
        "ix_case_event_case_id_occurred_at", "case_event", ["case_id", "occurred_at"], unique=False
    )
    op.create_index(op.f("ix_case_event_passage_id"), "case_event", ["passage_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_case_event_passage_id"), table_name="case_event")
    op.drop_index("ix_case_event_case_id_occurred_at", table_name="case_event")
    op.drop_index(op.f("ix_case_event_case_id"), table_name="case_event")
    op.drop_table("case_event")

    bind = op.get_bind()
    for enum in reversed(ALL_ENUMS):
        enum.drop(bind, checkfirst=True)
