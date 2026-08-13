"""add hobbista slug

Revision ID: a1f3c9d2e8b4
Revises: 8ecdf11e762d
Create Date: 2026-08-13 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
import re
import unicodedata


# revision identifiers, used by Alembic.
revision = 'a1f3c9d2e8b4'
down_revision = '8ecdf11e762d'
branch_labels = None
depends_on = None


def _slugify(text):
    text = unicodedata.normalize('NFKD', text)
    text = text.encode('ascii', 'ignore').decode('ascii')
    text = re.sub(r'[^\w\s-]', '', text).strip().lower()
    return re.sub(r'[-\s]+', '-', text) or 'artigiano'


def upgrade():
    # Aggiunge colonna slug (nullable per ora, poi popoliamo)
    op.add_column(
        'hobbista_accounts',
        sa.Column('slug', sa.String(120), nullable=True)
    )

    # Popola gli account esistenti con slug derivato da nome_visualizzato
    conn = op.get_bind()
    accounts = conn.execute(
        sa.text("SELECT id, nome_visualizzato FROM hobbista_accounts ORDER BY id")
    ).fetchall()

    used_slugs = set()
    for row in accounts:
        acc_id, nome = row[0], row[1]
        base = _slugify(nome) or f'artigiano-{acc_id}'
        slug = base
        counter = 1
        while slug in used_slugs:
            slug = f'{base}-{counter}'
            counter += 1
        used_slugs.add(slug)
        conn.execute(
            sa.text("UPDATE hobbista_accounts SET slug = :slug WHERE id = :id"),
            {'slug': slug, 'id': acc_id}
        )

    # Aggiunge unique index
    op.create_index('ix_hobbista_accounts_slug', 'hobbista_accounts', ['slug'], unique=True)


def downgrade():
    op.drop_index('ix_hobbista_accounts_slug', table_name='hobbista_accounts')
    op.drop_column('hobbista_accounts', 'slug')
