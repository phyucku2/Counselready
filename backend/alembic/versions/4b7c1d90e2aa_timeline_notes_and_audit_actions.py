"""timeline correction notes and audit actions

Adds `case_event_note` — corrections recorded beside an entry rather than on top of it
— and the three audit actions the timeline routes record.

Revision ID: 4b7c1d90e2aa
Revises: 00002f9f0461
Create Date: 2026-07-29 00:00:00.000000+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "4b7c1d90e2aa"
down_revision: str | None = "00002f9f0461"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The vocabulary as it stood before this revision — needed verbatim by the downgrade,
# because PostgreSQL can add an enum value but cannot remove one.
PREVIOUS_VALUES = (
    "case_created",
    "case_read",
    "case_list",
    "document_uploaded",
    "document_list",
    "document_read",
)
NEW_VALUES = ("event_created", "event_list", "event_note_created")


def upgrade() -> None:
    for value in NEW_VALUES:
        op.execute(f"ALTER TYPE case_action ADD VALUE IF NOT EXISTS '{value}'")

    op.create_table(
        "case_event_note",
        sa.Column("event_id", sa.UUID(), nullable=False),
        sa.Column("author_user_id", sa.UUID(), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
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
        sa.ForeignKeyConstraint(
            ["author_user_id"],
            ["user_account.id"],
            name=op.f("fk_case_event_note_author_user_id_user_account"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["case_event.id"],
            name=op.f("fk_case_event_note_event_id_case_event"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_case_event_note")),
    )
    op.create_index(
        "ix_case_event_note_event_created",
        "case_event_note",
        ["event_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    """Drop the table, then rebuild the enum without the new values.

    There is no `DROP VALUE`, so the type is recreated and the column recast. Rows
    carrying a value that no longer exists are deleted first: this is an audit table,
    and silently rewriting a recorded action to a different one would be worse than
    dropping the row and leaving a gap.
    """
    op.drop_index("ix_case_event_note_event_created", table_name="case_event_note")
    op.drop_table("case_event_note")

    quoted = ", ".join(f"'{value}'" for value in PREVIOUS_VALUES)
    dropped = ", ".join(f"'{value}'" for value in NEW_VALUES)
    op.execute(f"DELETE FROM case_audit_event WHERE action::text IN ({dropped})")  # noqa: S608
    op.execute("ALTER TYPE case_action RENAME TO case_action_old")
    op.execute(f"CREATE TYPE case_action AS ENUM ({quoted})")
    op.execute(
        "ALTER TABLE case_audit_event ALTER COLUMN action"
        " TYPE case_action USING action::text::case_action"
    )
    op.execute("DROP TYPE case_action_old")
