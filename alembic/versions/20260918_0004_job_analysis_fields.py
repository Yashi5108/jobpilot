"""Add job AI analysis fields.

Revision ID: 20260918_0004
Revises: 20260918_0003
Create Date: 2026-09-18 22:10:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260918_0004"
down_revision: str | None = "20260918_0003"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "jobs",
        sa.Column(
            "analysis_status",
            sa.String(length=50),
            nullable=False,
            server_default="NOT_ANALYZED",
        ),
    )
    op.add_column("jobs", sa.Column("analysis_result", sa.JSON(), nullable=True))
    op.add_column(
        "jobs", sa.Column("analyzed_at", sa.DateTime(timezone=True), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("jobs", "analyzed_at")
    op.drop_column("jobs", "analysis_result")
    op.drop_column("jobs", "analysis_status")
