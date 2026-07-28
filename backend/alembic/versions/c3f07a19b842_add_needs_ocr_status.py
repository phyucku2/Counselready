"""add needs_ocr document status

Text-layer extraction can read some pages and not others: a scanned exhibit stapled
into a native PDF is routine. `needs_ocr` records that honestly, where `complete`
would claim the document had been understood.

PostgreSQL has no `ALTER TYPE ... DROP VALUE`, so the downgrade rebuilds the type.
Rows holding the removed value are moved back to `pending` first — the state they
would have been in before this migration existed — rather than being orphaned or
silently dropped.

Revision ID: c3f07a19b842
Revises: 8a1be962755b
Create Date: 2026-07-28 00:31:00.000000+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c3f07a19b842"
down_revision: str | None = "8a1be962755b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

WITHOUT_NEEDS_OCR = ("pending", "processing", "complete", "failed")


def upgrade() -> None:
    # Permitted inside a transaction on PostgreSQL 12+, provided the new value is not
    # *used* in the same transaction — this migration only declares it.
    op.execute("ALTER TYPE ocr_status ADD VALUE IF NOT EXISTS 'needs_ocr' AFTER 'processing'")


def downgrade() -> None:
    op.execute(sa.text("UPDATE document SET ocr_status = 'pending' WHERE ocr_status = 'needs_ocr'"))

    values = ", ".join(f"'{value}'" for value in WITHOUT_NEEDS_OCR)
    op.execute("ALTER TYPE ocr_status RENAME TO ocr_status_old")
    op.execute(f"CREATE TYPE ocr_status AS ENUM ({values})")
    op.execute(
        "ALTER TABLE document ALTER COLUMN ocr_status TYPE ocr_status "
        "USING ocr_status::text::ocr_status"
    )
    op.execute("DROP TYPE ocr_status_old")
