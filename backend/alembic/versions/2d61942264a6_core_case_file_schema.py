"""core case file schema

Creates the citation spine: a case owns documents, a document owns pages, a page owns
passages, and every extracted fact points at a passage by a NOT NULL foreign key
(ADR-0001 §2).

Enum types are created and dropped explicitly rather than implicitly by `create_table`.
Left implicit, `CREATE TYPE` runs as a side effect of the first table that references
the type and is never dropped on downgrade — so downgrade-then-upgrade fails with
"type already exists".

Revision ID: 2d61942264a6
Revises: none
Create Date: 2026-07-27 23:48:25.996339+00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "2d61942264a6"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

jurisdiction = postgresql.ENUM("florida", name="jurisdiction", create_type=False)

party_role = postgresql.ENUM(
    "petitioner",
    "respondent",
    "child",
    "counsel",
    "guardian_ad_litem",
    "evaluator",
    "judge",
    "other",
    name="party_role",
    create_type=False,
)

document_kind = postgresql.ENUM(
    "unclassified",
    "petition",
    "motion",
    "response",
    "order",
    "notice",
    "financial_affidavit",
    "parenting_plan",
    "evaluation",
    "correspondence",
    "exhibit",
    "other",
    name="document_kind",
    create_type=False,
)

ingest_source = postgresql.ENUM(
    "upload", "camera", "email", name="ingest_source", create_type=False
)

ocr_status = postgresql.ENUM(
    "pending", "processing", "complete", "failed", name="ocr_status", create_type=False
)

fact_field = postgresql.ENUM(
    "case_number",
    "court",
    "judge",
    "document_kind",
    "filed_date",
    "served_date",
    "party_name",
    "counsel_name",
    "requested_relief",
    "referenced_exhibit",
    "referenced_date",
    "monetary_amount",
    name="fact_field",
    create_type=False,
)

ALL_ENUMS = (
    jurisdiction,
    party_role,
    document_kind,
    ingest_source,
    ocr_status,
    fact_field,
)


def upgrade() -> None:
    bind = op.get_bind()
    for enum in ALL_ENUMS:
        enum.create(bind, checkfirst=True)

    op.create_table(
        "user_account",
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
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
        sa.PrimaryKeyConstraint("id", name=op.f("pk_user_account")),
        sa.UniqueConstraint("email", name=op.f("uq_user_account_email")),
    )

    op.create_table(
        "case",
        sa.Column("owner_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("jurisdiction", jurisdiction, nullable=False),
        sa.Column("court", sa.String(length=200), nullable=True),
        sa.Column("case_number", sa.String(length=100), nullable=True),
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
            ["owner_id"],
            ["user_account.id"],
            name=op.f("fk_case_owner_id_user_account"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_case")),
    )
    op.create_index(op.f("ix_case_owner_id"), "case", ["owner_id"], unique=False)

    op.create_table(
        "party",
        sa.Column("case_id", sa.UUID(), nullable=False),
        sa.Column("display_name", sa.String(length=200), nullable=False),
        sa.Column("role", party_role, nullable=False),
        sa.Column("is_minor", sa.Boolean(), nullable=False),
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
            ["case_id"], ["case.id"], name=op.f("fk_party_case_id_case"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_party")),
        sa.UniqueConstraint(
            "case_id",
            "display_name",
            "role",
            name=op.f("uq_party_case_id_display_name_role"),
        ),
    )
    op.create_index(op.f("ix_party_case_id"), "party", ["case_id"], unique=False)

    op.create_table(
        "document",
        sa.Column("case_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(length=300), nullable=False),
        sa.Column("kind", document_kind, nullable=False),
        sa.Column("ingest_source", ingest_source, nullable=False),
        sa.Column("storage_key", sa.String(length=500), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("filed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("served_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("page_count", sa.Integer(), nullable=False),
        sa.Column("ocr_status", ocr_status, nullable=False),
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
        sa.CheckConstraint("page_count >= 0", name=op.f("ck_document_page_count_non_negative")),
        sa.ForeignKeyConstraint(
            ["case_id"], ["case.id"], name=op.f("fk_document_case_id_case"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document")),
        sa.UniqueConstraint(
            "case_id", "content_hash", name=op.f("uq_document_case_id_content_hash")
        ),
    )
    op.create_index(op.f("ix_document_case_id"), "document", ["case_id"], unique=False)

    op.create_table(
        "document_page",
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("ocr_confidence", sa.Float(), nullable=True),
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
            "ocr_confidence IS NULL OR (ocr_confidence >= 0 AND ocr_confidence <= 1)",
            name=op.f("ck_document_page_ocr_confidence_is_a_fraction"),
        ),
        sa.CheckConstraint("page_number >= 1", name=op.f("ck_document_page_page_number_positive")),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["document.id"],
            name=op.f("fk_document_page_document_id_document"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_document_page")),
        sa.UniqueConstraint(
            "document_id", "page_number", name=op.f("uq_document_page_document_id_page_number")
        ),
    )
    op.create_index(
        op.f("ix_document_page_document_id"), "document_page", ["document_id"], unique=False
    )

    op.create_table(
        "passage",
        sa.Column("page_id", sa.UUID(), nullable=False),
        sa.Column("start_offset", sa.Integer(), nullable=False),
        sa.Column("end_offset", sa.Integer(), nullable=False),
        sa.Column("quote", sa.Text(), nullable=False),
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
            "end_offset > start_offset", name=op.f("ck_passage_end_offset_after_start")
        ),
        sa.CheckConstraint("start_offset >= 0", name=op.f("ck_passage_start_offset_non_negative")),
        sa.ForeignKeyConstraint(
            ["page_id"],
            ["document_page.id"],
            name=op.f("fk_passage_page_id_document_page"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_passage")),
    )
    op.create_index(op.f("ix_passage_page_id"), "passage", ["page_id"], unique=False)

    op.create_table(
        "extracted_fact",
        sa.Column("document_id", sa.UUID(), nullable=False),
        sa.Column("passage_id", sa.UUID(), nullable=False),
        sa.Column("field", fact_field, nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("extractor_version", sa.String(length=100), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
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
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name=op.f("ck_extracted_fact_confidence_is_a_fraction"),
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["document.id"],
            name=op.f("fk_extracted_fact_document_id_document"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["passage_id"],
            ["passage.id"],
            name=op.f("fk_extracted_fact_passage_id_passage"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_extracted_fact")),
        sa.UniqueConstraint(
            "passage_id",
            "field",
            "extractor_version",
            name=op.f("uq_extracted_fact_passage_id_field_extractor_version"),
        ),
    )
    op.create_index(
        op.f("ix_extracted_fact_document_id"), "extracted_fact", ["document_id"], unique=False
    )
    op.create_index(
        op.f("ix_extracted_fact_passage_id"), "extracted_fact", ["passage_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_extracted_fact_passage_id"), table_name="extracted_fact")
    op.drop_index(op.f("ix_extracted_fact_document_id"), table_name="extracted_fact")
    op.drop_table("extracted_fact")
    op.drop_index(op.f("ix_passage_page_id"), table_name="passage")
    op.drop_table("passage")
    op.drop_index(op.f("ix_document_page_document_id"), table_name="document_page")
    op.drop_table("document_page")
    op.drop_index(op.f("ix_document_case_id"), table_name="document")
    op.drop_table("document")
    op.drop_index(op.f("ix_party_case_id"), table_name="party")
    op.drop_table("party")
    op.drop_index(op.f("ix_case_owner_id"), table_name="case")
    op.drop_table("case")
    op.drop_table("user_account")

    bind = op.get_bind()
    for enum in reversed(ALL_ENUMS):
        enum.drop(bind, checkfirst=True)
