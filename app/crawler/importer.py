"""
app/crawler/importer.py
Normalizza i risultati grezzi e li importa nel DB come bozze.
"""
import logging
import re
from datetime import date, timedelta
from typing import List, Dict, Optional, Tuple

from sqlalchemy.exc import SQLAlchemyError

log = logging.getLogger(__name__)


def normalizza(raw: Dict, testo_pagina: str = '') -> Optional[Dict]:
    """
    Prende un risultato grezzo e ritorna un dict normalizzato pronto
    per la creazione del Mercatino, oppure None se non abbastanza dati.
    """
    from .parser import estrai_date, estrai_luogo, testo_e_mercatino

    # Testo su cui lavorare: snippet + eventuale testo completo pagina
    testo = (
        raw.get('testo_completo') or
        raw.get('snippet', '') + ' ' + testo_pagina
    )

    if not testo_e_mercatino(testo + raw.get('titolo', '')):
        return None

    # Date
    data_inizio, data_fine = estrai_date(testo)
    if not data_inizio:
        # Prova dal titolo
        data_inizio, data_fine = estrai_date(raw.get('titolo', ''))
    if not data_inizio:
        return None  # Senza data non importiamo

    # Scarta date già passate di più di 1 mese
    if data_inizio < date.today() - timedelta(days=30):
        return None

    # Luogo
    citta, provincia, regione = estrai_luogo(testo)
    if not citta:
        citta, provincia, regione = estrai_luogo(raw.get('titolo', ''))
    if not regione and not citta:
        # Senza luogo è troppo vago
        return None

    # Titolo: usa quello del risultato o costruisci
    titolo = raw.get('titolo', '').strip()
    titolo = re.sub(r'\s+', ' ', titolo)[:200]
    if not titolo:
        titolo = f'Mercatino{" a " + citta if citta else ""}'

    # Descrizione (snippet pulito)
    descrizione = raw.get('snippet', '')[:1000].strip()

    return {
        'titolo': titolo,
        'descrizione': descrizione,
        'citta': citta[:100],
        'regione': regione[:100],
        'provincia': provincia[:5] if provincia else '',
        'data_inizio': data_inizio,
        'data_fine': data_fine or data_inizio,
        'fonte_crawler': raw.get('url', '')[:500],
        'pubblicato': False,  # sempre bozza per revisione
    }


def salva_nel_db(
    normalizzati: List[Dict],
    bot_user_id: int,
) -> Tuple[int, int]:
    """
    Salva i mercatini normalizzati nel DB come bozze.
    Ritorna (salvati, saltati_duplicati).
    """
    from app import db
    from app.models.mercatino import Mercatino
    from sqlalchemy import func

    salvati = 0
    saltati = 0

    for m in normalizzati:
        try:
            # Deduplicazione: stesso titolo+città+data_inizio
            esiste = db.session.query(Mercatino).filter(
                func.lower(Mercatino.titolo) == m['titolo'].lower(),
                func.lower(Mercatino.citta) == m['citta'].lower(),
                Mercatino.data_inizio == m['data_inizio'],
            ).first()

            if esiste:
                # Aggiorna fonte_crawler se mancante
                if not esiste.fonte_crawler and m.get('fonte_crawler'):
                    esiste.fonte_crawler = m['fonte_crawler']
                    db.session.commit()
                saltati += 1
                continue

            nuovo = Mercatino(
                titolo=m['titolo'],
                descrizione=m.get('descrizione', ''),
                citta=m['citta'],
                regione=m['regione'],
                provincia=m.get('provincia', ''),
                data_inizio=m['data_inizio'],
                data_fine=m['data_fine'],
                fonte_crawler=m.get('fonte_crawler', ''),
                pubblicato=False,
                organizzatore_id=bot_user_id,
                ricorrenza='nessuna',
            )
            db.session.add(nuovo)
            db.session.commit()
            salvati += 1
            log.info(f'[import] Salvato: {nuovo.titolo} ({nuovo.citta}) {nuovo.data_inizio}')

        except SQLAlchemyError as e:
            db.session.rollback()
            log.error(f'[import] Errore DB: {e}')

    return salvati, saltati


def ottieni_bot_user_id(app) -> Optional[int]:
    """
    Ritorna l'ID dell'utente bot/admin da usare come organizzatore
    per i mercatini importati dal crawler.
    Cerca prima un utente con email 'crawler@mercatini.bot',
    se non esiste lo crea.
    """
    from app import db
    from app.models.user import User
    import secrets

    BOT_EMAIL = 'crawler@mercatini.bot'

    with app.app_context():
        bot = User.query.filter_by(email=BOT_EMAIL).first()
        if bot:
            return bot.id

        # Crea utente bot
        try:
            from flask_bcrypt import Bcrypt
            bcrypt = Bcrypt(app)
            pw = secrets.token_urlsafe(32)
            bot = User(
                email=BOT_EMAIL,
                nome='Bot Crawler',
                cognome='',
                password_hash=bcrypt.generate_password_hash(pw).decode('utf-8'),
                ruolo='admin',
                email_verified=True,
                notifiche_email=False,
            )
            db.session.add(bot)
            db.session.commit()
            log.info(f'[import] Utente bot creato con ID {bot.id}')
            return bot.id
        except Exception as e:
            db.session.rollback()
            log.error(f'[import] Impossibile creare bot user: {e}')
            # Fallback: usa il primo admin
            admin = User.query.filter_by(ruolo='admin').first()
            return admin.id if admin else None
