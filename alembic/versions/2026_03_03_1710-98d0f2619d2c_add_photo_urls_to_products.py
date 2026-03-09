"""add photo_urls to products

Revision ID: 98d0f2619d2c
Revises: ceaa8d9933c0
Create Date: 2026-03-03 17:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "98d0f2619d2c"
down_revision: Union[str, Sequence[str], None] = "ceaa8d9933c0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "products",
        sa.Column(
            "photo_urls",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'::json"),
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("products", "photo_urls")
