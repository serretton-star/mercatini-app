"""user provincia residenza notifiche

Revision ID: 05b7c124f0c6
Revises: 40777ca87efe
Create Date: 2026-07-27 10:11:01.094207

"""
from alembic import op
import sqlalchemy as sa


revision = '05b7c124f0c6'
down_revision = '40777ca87efe'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.add_column(sa.Column('provincia_residenza', sa.String(length=5), nullable=True))
        # server_default='true' consente di aggiungere la colonna su righe esistenti
        batch_op.add_column(sa.Column('notifiche_email', sa.Boolean(),
                                      nullable=False,
                                      server_default=sa.text('true')))
        batch_op.create_index(batch_op.f('ix_users_provincia_residenza'),
                              ['provincia_residenza'], unique=False)


def downgrade():
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_users_provincia_residenza'))
        batch_op.drop_column('notifiche_email')
        batch_op.drop_column('provincia_residenza')
