"""Create the table of cached AI reviews.

Revision ID: metadata_assistant_002
Revises: metadata_assistant_001
"""

from alembic import op
import sqlalchemy as sa


revision = "metadata_assistant_002"
down_revision = "metadata_assistant_001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "metadata_assistant_review_cache",
        sa.Column("digest", sa.String(length=64), nullable=False),
        sa.Column("package_id", sa.String(length=36), nullable=False),
        sa.Column("result", sa.Text(), nullable=False),
        sa.Column("created", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("digest"),
    )
    op.create_index("idx_ma_review_cache_package", "metadata_assistant_review_cache", ["package_id"])


def downgrade():
    op.drop_index("idx_ma_review_cache_package", table_name="metadata_assistant_review_cache")
    op.drop_table("metadata_assistant_review_cache")
