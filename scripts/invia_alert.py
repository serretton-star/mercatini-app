#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Invia notifiche email agli utenti con Alert attivi che hanno nuovi mercatini.
Da eseguire ogni notte: crontab -> 0 8 * * * /var/www/mercatini/scripts/run_alert.sh
"""
import os, sys, smtplib, logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime, date

# Setup path Flask
sys.path.insert(0, '/var/www/mercatini')
os.chdir('/var/www/mercatini')

from dotenv import load_dotenv
load_dotenv('/var/www/mercatini/.env')

from app import create_app, db
from app.models import Alert, Mercatino, User

logging.basicConfig(
    filename='/var/www/mercatini/logs/alert_cron.log',
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
)
log = logging.getLogger(__name__)

SMTP_HOST   = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
SMTP_PORT   = int(os.environ.get('MAIL_PORT', 587))
SMTP_USER   = os.environ.get('MAIL_USERNAME', '')
SMTP_PASS   = os.environ.get('MAIL_PASSWORD', '')
MAIL_FROM   = os.environ.get('MAIL_DEFAULT_SENDER', SMTP_USER)
BASE_URL    = os.environ.get('BASE_URL', 'https://mercatini.blog')


def _match_alert(alert: Alert, m: Mercatino) -> bool:
    """Verifica se un mercatino corrisponde ai criteri di un alert."""
    # Provincia
    if alert.provincia:
        prov = (m.provincia or '').lower()
        if alert.provincia.lower() not in prov:
            return False
    # Categoria
    if alert.categoria_id:
        if m.categoria_id != alert.categoria_id:
            return False
    # Parole chiave (almeno una deve apparire in titolo o descrizione)
    if alert.parole_chiave:
        testo = f"{m.titolo} {m.descrizione or ''} {m.citta or ''}".lower()
        keywords = [k.strip().lower() for k in alert.parole_chiave.split(',') if k.strip()]
        if keywords and not any(k in testo for k in keywords):
            return False
    return True


def _build_email_html(user: User, matches: list) -> str:
    items = ''
    for m in matches:
        d_ini = m.data_inizio.strftime('%d/%m/%Y') if m.data_inizio else '?'
        d_fin = m.data_fine.strftime('%d/%m/%Y') if m.data_fine else '?'
        url   = f'{BASE_URL}/mercatini/{m.id}'
        items += f"""
        <tr>
          <td style="padding:10px;border-bottom:1px solid #eee;">
            <a href="{url}" style="color:#2563eb;font-weight:bold;text-decoration:none;">{m.titolo}</a><br>
            <span style="color:#666;font-size:13px;">📍 {m.citta or ''}, {m.provincia or ''} &nbsp;|&nbsp; 📅 {d_ini}–{d_fin}</span>
          </td>
        </tr>"""
    return f"""
    <html><body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;color:#333;">
      <div style="background:#2563eb;padding:20px;border-radius:8px 8px 0 0;">
        <h1 style="color:white;margin:0;font-size:22px;">🎪 Nuovi mercatini per te!</h1>
      </div>
      <div style="padding:20px;background:#fff;border:1px solid #e5e7eb;border-top:0;">
        <p>Ciao {user.nome_completo or user.email},<br>
        abbiamo trovato <strong>{len(matches)} nuov{'o' if len(matches)==1 else 'i'} mercatin{'o' if len(matches)==1 else 'i'}</strong>
        che corrispond{'e' if len(matches)==1 else 'ono'} ai tuoi alert.</p>
        <table width="100%" cellspacing="0" cellpadding="0">{items}</table>
        <p style="margin-top:20px;">
          <a href="{BASE_URL}/mercatini" style="background:#2563eb;color:white;padding:10px 20px;
          border-radius:6px;text-decoration:none;font-weight:bold;">Scopri tutti i mercatini</a>
        </p>
        <p style="font-size:12px;color:#999;margin-top:30px;">
          Gestisci i tuoi alert su <a href="{BASE_URL}/account/profilo">profilo</a>.
        </p>
      </div>
    </html>"""


def _send_email(to: str, subject: str, html: str):
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From']    = MAIL_FROM
    msg['To']      = to
    msg.attach(MIMEText(html, 'html', 'utf-8'))
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as s:
        s.ehlo()
        s.starttls()
        s.login(SMTP_USER, SMTP_PASS)
        s.sendmail(MAIL_FROM, [to], msg.as_bytes())


def run():
    app = create_app()
    with app.app_context():
        oggi = date.today()
        alerts = Alert.query.filter_by(attivo=True).all()
        log.info(f"Alert attivi: {len(alerts)}")

        # Recupera mercatini pubblicati con data_fine >= oggi
        mercatini_attivi = (
            Mercatino.query
            .filter_by(pubblicato=True)
            .filter(Mercatino.data_fine >= oggi)
            .all()
        )

        # Raggruppa per utente per inviare una sola email
        notifiche = {}  # user_id -> (user, [mercatini])

        for alert in alerts:
            # Trova mercatini nuovi dall'ultimo invio
            soglia = alert.ultima_notifica_il or datetime(2000, 1, 1)
            nuovi = [
                m for m in mercatini_attivi
                if m.created_at and m.created_at > soglia
                and _match_alert(alert, m)
            ]
            if not nuovi:
                continue

            user = User.query.get(alert.user_id)
            if not user or not user.email:
                continue

            if user.id not in notifiche:
                notifiche[user.id] = (user, set())
            for m in nuovi:
                notifiche[user.id][1].add(m.id)

            alert.ultima_notifica_il = datetime.utcnow()

        db.session.commit()
        log.info(f"Utenti da notificare: {len(notifiche)}")

        for user_id, (user, mercatino_ids) in notifiche.items():
            matches = [m for m in mercatini_attivi if m.id in mercatino_ids]
            try:
                html = _build_email_html(user, matches)
                _send_email(
                    user.email,
                    f"🎪 {len(matches)} nuov{'o' if len(matches)==1 else 'i'} mercatin{'o' if len(matches)==1 else 'i'} per te!",
                    html
                )
                log.info(f"Email inviata a {user.email} con {len(matches)} mercatini")
            except Exception as e:
                log.error(f"Errore invio email a {user.email}: {e}")


if __name__ == '__main__':
    run()
    print("Alert completati.")
