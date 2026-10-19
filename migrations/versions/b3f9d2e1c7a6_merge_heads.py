"""merge heads: ricorrenza + hobbista slug

Revision ID: b3f9d2e1c7a6
Revises: a1f3c9d2e8b4, a2f8c1d3e9b5
Create Date: 2026-10-19 19:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'b3f9d2e1c7a6'
down_revision = ('a1f3c9d2e8b4', 'a2f8c1d3e9b5')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
