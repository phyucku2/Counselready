"""${message}

Revision ID: ${up_revision}
% if down_revision:
Revises: ${down_revision | comma,n}
% else:
Revises: none
% endif
Create Date: ${create_date}
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
${imports if imports else ""}
revision: str = "${up_revision}"
down_revision: str | None = ${'"{}"'.format(down_revision) if down_revision else "None"}
branch_labels: str | Sequence[str] | None = ${repr(branch_labels) if branch_labels else "None"}
depends_on: str | Sequence[str] | None = ${repr(depends_on) if depends_on else "None"}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
