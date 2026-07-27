"""Flask CLI commands — esegui con: flask <comando>"""
import click
from flask import current_app
from app import db
from app.models import Categoria


CATEGORIE_DEFAULT = [
    'Artigianato',
    'Cibo & Vino',
    'Antiquariato',
    'Biologico & Naturale',
    'Design & Arte',
    'Natale & Feste',
    'Vintage & Usato',
    'Fiori & Piante',
    'Libri & Cultura',
    'Gioielli & Bijoux',
    'Tessuti & Moda',
    'Ceramica & Ceramiche',
    'Legno & Falegnameria',
]


def register_commands(app):
    @app.cli.command('seed-db')
    def seed_db():
        """Inserisce le categorie di default nel DB (idempotente)."""
        nuove = 0
        for nome in CATEGORIE_DEFAULT:
            from slugify import slugify
            slug = slugify(nome)
            if not Categoria.query.filter_by(slug=slug).first():
                db.session.add(Categoria(nome))
                nuove += 1
        db.session.commit()
        click.echo(f'[OK] Seed completato: {nuove} categorie aggiunte '
                   f'({len(CATEGORIE_DEFAULT) - nuove} già presenti).')

    @app.cli.command('create-admin')
    @click.argument('email')
    def create_admin(email):
        """Promuove un utente esistente ad admin. Uso: flask create-admin EMAIL"""
        from app.models import User
        u = User.query.filter_by(email=email).first()
        if not u:
            click.echo(f'[ERR] Utente {email} non trovato.')
            return
        u.ruolo = 'admin'
        db.session.commit()
        click.echo(f'[OK] {u.nome_completo} ({email}) promosso admin.')
