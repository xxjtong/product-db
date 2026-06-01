"""initial_schema

Revision ID: 7db0c6d785b3
Revises:
Create Date: 2026-06-01 15:20:04.967205

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7db0c6d785b3'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create all tables from model metadata — fresh-install baseline."""
    from app.database import Base
    from app.models import *  # noqa: F401, F403 — register all models
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    """Drop all tables — reverse of initial schema."""
    from app.database import Base
    from app.models import *  # noqa: F401, F403
    Base.metadata.drop_all(bind=op.get_bind())
