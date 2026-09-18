"""Add parsed resume metadata fields.

Revision ID: 20260918_0002
Revises: 20260916_0001
Create Date: 2026-09-18 17:20:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260918_0002"
down_revision: str | None = "20260916_0001"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "resumes", sa.Column("mime_type", sa.String(length=100), nullable=True)
    )
    op.add_column("resumes", sa.Column("file_size_bytes", sa.Integer(), nullable=True))
    op.add_column("resumes", sa.Column("page_count", sa.Integer(), nullable=True))
    op.add_column(
        "resumes", sa.Column("parse_status", sa.String(length=50), nullable=True)
    )
    op.add_column("resumes", sa.Column("raw_text", sa.String(), nullable=True))
    op.add_column("resumes", sa.Column("normalized_text", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("resumes", "normalized_text")
    op.drop_column("resumes", "raw_text")
    op.drop_column("resumes", "parse_status")
    op.drop_column("resumes", "page_count")
    op.drop_column("resumes", "file_size_bytes")
    op.drop_column("resumes", "mime_type")
