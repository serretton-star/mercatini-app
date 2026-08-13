"""
app/tasks.py
Task schedulati per mercatini.blog — digest foto artigiani hobbisti.
"""
import logging
from collections import defaultdict

log = logging.getLogger(__name__)


def invia_digest_foto_hobbisti(app):
    """
    Job giornaliero (default ore 18:00 Europe/Rome).
    Per ogni utente che segue almeno un artigiano con foto nuove,
    invia UN'unica email digest raggruppata.
    Idempotente: righe con inclusa_in_digest=True vengono saltate.
    """
    with app.app_context():
        from flask import render_template
        from flask_mail import Message
        from app import db, mail
        from app.models.follow import HobbistaFollow, HobbistaFotoDigestQueue
        from app.models.user import User
        from app.models.hobbisti import HobbistaAccount

        # 1. Foto in attesa
        items = (
            db.session.query(HobbistaFotoDigestQueue)
            .filter_by(inclusa_in_digest=False)
            .order_by(HobbistaFotoDigestQueue.hobbista_id,
                      HobbistaFotoDigestQueue.creato_il)
            .all()
        )
        if not items:
            log.info('[digest_foto] Nessuna foto in coda. Skip.')
            return

        # 2. Raggruppa per hobbista
        foto_per_hobbista = defaultdict(list)
        for item in items:
            foto_per_hobbista[item.hobbista_id].append(item)

        # 3. Mappa user -> [(hobbista, [queue_items])]
        digest_per_utente = defaultdict(list)
        for hobbista_id, queue_items in foto_per_hobbista.items():
            hobbista = db.session.get(HobbistaAccount, hobbista_id)
            if not hobbista:
                continue
            followers = (
                HobbistaFollow.query
                .filter_by(hobbista_id=hobbista_id, attivo=True)
                .all()
            )
            for follow in followers:
                user = db.session.get(User, follow.user_id)
                if not user:
                    continue
                if not user.notifiche_email:
                    continue
                if not getattr(user, 'notifiche_digest_foto_hobbisti', True):
                    continue
                digest_per_utente[follow.user_id].append((hobbista, queue_items))

        # 4. Invia email per utente
        inviati = 0
        for user_id, sezioni in digest_per_utente.items():
            user = db.session.get(User, user_id)
            if not user:
                continue
            try:
                from itsdangerous import URLSafeTimedSerializer
                _s = URLSafeTimedSerializer(app.config['SECRET_KEY'])
                unsub_token = _s.dumps(user.id, salt='hobbista-follow-unsub-v1')
                html = render_template(
                    'email/hobbisti_digest_foto.html',
                    user=user,
                    sezioni=sezioni,
                    unsub_token=unsub_token,
                )
                msg = Message(
                    subject='Le novità degli artigiani che segui — mercatini.blog',
                    recipients=[user.email],
                )
                msg.html = html
                if not app.config.get('MAIL_SUPPRESS_SEND'):
                    mail.send(msg)
                    inviati += 1
                else:
                    log.info(f'[digest_foto] [SOPPRESSO] {user.email}')
                    inviati += 1
            except Exception as exc:
                log.error(f'[digest_foto] Errore per {user.email}: {exc}')

        # 5. Marca come processate
        for item in items:
            item.inclusa_in_digest = True
        db.session.commit()

        log.info(
            f'[digest_foto] OK — {inviati} email, {len(items)} foto processate.'
        )


def invia_notifica_evento(app, partecipazione_id):
    """
    Invio immediato (sincrono) notifica evento a tutti i follower attivi.
    Chiamato dalla route dichiara_partecipazione dopo il commit.
    """
    with app.app_context():
        from flask import render_template
        from flask_mail import Message
        from app import db, mail
        from app.models.follow import HobbistaFollow, HobbistaEventoPartecipazione
        from app.models.user import User

        partecipazione = db.session.get(HobbistaEventoPartecipazione, partecipazione_id)
        if not partecipazione or partecipazione.notifica_inviata:
            return

        hobbista = partecipazione.hobbista
        followers = (
            HobbistaFollow.query
            .filter_by(hobbista_id=hobbista.id, attivo=True)
            .all()
        )

        inviati = 0
        for follow in followers:
            user = db.session.get(User, follow.user_id)
            if not user:
                continue
            if not user.notifiche_email:
                continue
            if not getattr(user, 'notifiche_eventi_hobbisti', True):
                continue
            try:
                from itsdangerous import URLSafeTimedSerializer
                _s = URLSafeTimedSerializer(app.config['SECRET_KEY'])
                unsub_token = _s.dumps(user.id, salt='hobbista-follow-unsub-v1')
                html = render_template(
                    'email/hobbisti_evento_notifica.html',
                    user=user,
                    hobbista=hobbista,
                    partecipazione=partecipazione,
                    unsub_token=unsub_token,
                )
                msg = Message(
                    subject=f'{hobbista.nome_visualizzato} parteciperà a {partecipazione.nome_evento_display} — mercatini.blog',
                    recipients=[user.email],
                )
                msg.html = html
                if not app.config.get('MAIL_SUPPRESS_SEND'):
                    mail.send(msg)
                    inviati += 1
                else:
                    log.info(f'[evento_notifica] [SOPPRESSO] {user.email}')
                    inviati += 1
            except Exception as exc:
                log.error(f'[evento_notifica] Errore per {user.email}: {exc}')

        partecipazione.notifica_inviata = True
        db.session.commit()
        log.info(
            f'[evento_notifica] OK — {inviati} notifiche per partecipazione {partecipazione_id}.'
        )
