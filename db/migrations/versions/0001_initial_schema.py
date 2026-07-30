"""Initial serving schema (dimensions, facts, pipeline audit).

Creates the full schema from the SQLAlchemy models. Kept DRY by delegating to
``Base.metadata`` so the migration never drifts from the ORM definitions.

Revision ID: 0001
Revises:
Create Date: 2026-07-30
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

from db.models.models import Base

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
