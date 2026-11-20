"""Create the table of translation proposals.

Revision ID: metadata_assistant_001
Revises:
"""

from alembic import op
import sqlalchemy as sa


revision = "metadata_assistant_001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "metadata_assistant_translation_proposal",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("package_id", sa.String(length=36), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("source_digest", sa.String(length=64), nullable=False),
        sa.Column("suggestions", sa.Text(), nullable=False),
        sa.Column("created", sa.DateTime(), nullable=False),
        sa.Column("decided", sa.DateTime(), nullable=True),
        sa.Column("decided_by", sa.String(length=100), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_ma_translation_proposal_package", "metadata_assistant_translation_proposal", ["package_id"])
    op.create_index("idx_ma_translation_proposal_status", "metadata_assistant_translation_proposal", ["status"])


def downgrade():
    op.drop_index("idx_ma_translation_proposal_status", table_name="metadata_assistant_translation_proposal")
    op.drop_index("idx_ma_translation_proposal_package", table_name="metadata_assistant_translation_proposal")
    op.drop_table("metadata_assistant_translation_proposal")
