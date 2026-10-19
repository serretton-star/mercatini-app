"""add ricorrenza fields to mercatini

Revision ID: a2f8c1d3e9b5
Revises: ef9b5b0d650a
Create Date: 2026-10-19 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = 'a2f8c1d3e9b5'
down_revision = 'ef9b5b0d650a'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('mercatini', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'ricorrenza', sa.String(length=20), nullable=False,
            server_default='nessuna'
        ))
        batch_op.add_column(sa.Column(
            'data_fine_ricorrenza', sa.Date(), nullable=True
        ))


def downgrade():
    with op.batch_alter_table('mercatini', schema=None) as batch_op:
        batch_op.drop_column('data_fine_ricorrenza')
        batch_op.drop_column('ricorrenza')
