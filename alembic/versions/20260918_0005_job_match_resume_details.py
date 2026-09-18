"""Add resume-scoped match fields and details.

Revision ID: 20260918_0005
Revises: 20260918_0004
Create Date: 2026-09-18 23:25:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260918_0005"
down_revision: str | None = "20260918_0004"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("job_matches", sa.Column("resume_id", sa.Integer(), nullable=True))
    op.add_column("job_matches", sa.Column("match_details", sa.JSON(), nullable=True))
    op.add_column(
        "job_matches",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    with op.batch_alter_table("job_matches") as batch_op:
        batch_op.create_foreign_key(
            "fk_job_matches_resume_id_resumes",
            "resumes",
            ["resume_id"],
            ["id"],
            ondelete="CASCADE",
        )
        batch_op.create_unique_constraint(
            "uq_job_matches_job_id_resume_id",
            ["job_id", "resume_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("job_matches") as batch_op:
        batch_op.drop_constraint("uq_job_matches_job_id_resume_id", type_="unique")
        batch_op.drop_constraint(
            "fk_job_matches_resume_id_resumes",
            type_="foreignkey",
        )
    op.drop_column("job_matches", "updated_at")
    op.drop_column("job_matches", "match_details")
    op.drop_column("job_matches", "resume_id")
