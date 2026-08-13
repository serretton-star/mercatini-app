"""
app/artigiani_auth/routes.py
Auth separata per hobbisti: registrazione, login, logout, verifica email.
Non usa Flask-Login — gestisce la sessione con session['hobbista_id'].
Google OAuth: TODO (non ancora presente nel progetto; integrare con Authlib in step successivo).
"""
import logging
from datetime import datetime, timezone

from flask import (render_template, redirect, url_for,
                   flash, request, session, current_app)
from flask_mail import Message
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature

from app import db, bcrypt, mail
from app.artigiani_auth import artigiani_auth
from app.models.hobbisti import HobbistaAccount

log = logging.getLogger(__name__)
SALT_VERIFY = 'hobbista-email-verify-v1'


def _serializer():
    return URLSafeTimedSerializer(current_app.config['SECRET_KEY'])


def _invia_email_verifica(hobbista, verify_url):
    try:
        msg = Message(
            'Conferma il tuo profilo artigiano — mercatini.blog',
            recipients=[hobbista.email]
        )
        msg.html = f"""
<p>Ciao <b>{hobbista.nome_visualizzato}</b>,</p>
<p>Grazie per aver creato il tuo profilo artigiano su mercatini.blog.</p>
<p>Clicca qui per confermare il tuo indirizzo email:</p>
<p><a href="{verify_url}" style="
  display:inline-block;padding:10px 20px;background:#C0522A;color:#fff;
  text-decoration:none;border-radius:6px;font-weight:bold
">Conferma email</a></p>
<p>Oppure copia questo link nel browser:<br>{verify_url}</p>
<p>Il link è valido per 24 ore.</p>
<p>— mercatini.blog</p>
"""
        mail.send(msg)
    except Exception as e:
        log.warning(f"Email verifica hobbista non inviata a {hobbista.email}: {e}")


# ── Registrazione ─────────────────────────────────────────────────────────────

@artigiani_auth.route('/registrati', methods=['GET', 'POST'])
def registrati():
    if session.get('hobbista_id'):
        return redirect(url_for('artigiani.dashboard'))

    if request.method == 'POST':
        nome       = request.form.get('nome_visualizzato', '').strip()
        email      = request.form.get('email', '').strip().lower()
        password   = request.form.get('password', '')
        instagram  = request.form.get('instagram_handle', '').strip() or None
        whatsapp   = request.form.get('whatsapp_number', '').strip() or None
        termini_ok = request.form.get('termini_accettati')

        errors = []
        if not nome:
            errors.append('Il nome visualizzato è obbligatorio.')
        if not email or '@' not in email:
            errors.append('Inserisci un indirizzo email valido.')
        if len(password) < 8:
            errors.append('La password deve avere almeno 8 caratteri.')
        if not termini_ok:
            errors.append('Devi accettare i Termini di Servizio per procedere.')

        if not errors and HobbistaAccount.query.filter_by(email=email).first():
            errors.append('Questa email è già registrata. Prova ad accedere.')

        if errors:
            for e in errors:
                flash(e, 'danger')
            return render_template('artigiani/auth/registrati.html',
                                   form=request.form)

        pw_hash  = bcrypt.generate_password_hash(password, rounds=12).decode('utf-8')
        hobbista = HobbistaAccount(
            nome_visualizzato    = nome,
            email                = email,
            password_hash        = pw_hash,
            instagram_handle     = instagram,
            whatsapp_number      = whatsapp,
            termini_accettati_il = datetime.now(timezone.utc),
            email_verificata     = False,
        )
        db.session.add(hobbista)
        db.session.commit()

        token      = _serializer().dumps(email, salt=SALT_VERIFY)
        verify_url = url_for('artigiani_auth.verifica_email',
                             token=token, _external=True)
        _invia_email_verifica(hobbista, verify_url)

        flash('Registrazione completata! Controlla la tua email per attivare il profilo.', 'success')
        return redirect(url_for('artigiani_auth.login'))

    return render_template('artigiani/auth/registrati.html', form={})


# ── Login ─────────────────────────────────────────────────────────────────────

@artigiani_auth.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('hobbista_id'):
        return redirect(url_for('artigiani.dashboard'))

    if request.method == 'POST':
        email    = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        hobbista = HobbistaAccount.query.filter_by(email=email).first()

        if (hobbista and hobbista.password_hash and
                bcrypt.check_password_hash(hobbista.password_hash, password)):

            if not hobbista.email_verificata:
                flash('Devi prima confermare la tua email. '
                      'Controlla la casella di posta.', 'warning')
                return render_template('artigiani/auth/login.html')

            if hobbista.stato.value == 'sospeso':
                flash('Il tuo account è stato sospeso. '
                      'Contattaci su WhatsApp per assistenza.', 'danger')
                return render_template('artigiani/auth/login.html')

            session['hobbista_id'] = hobbista.id
            hobbista.ultimo_accesso = datetime.now(timezone.utc)
            db.session.commit()

            next_page = request.args.get('next')
            flash(f'Benvenuto, {hobbista.nome_visualizzato}!', 'success')
            return redirect(next_page or url_for('artigiani.dashboard'))

        flash('Email o password non corretti.', 'danger')

    return render_template('artigiani/auth/login.html')


# ── Logout ────────────────────────────────────────────────────────────────────

@artigiani_auth.route('/logout')
def logout():
    session.pop('hobbista_id', None)
    flash('Sei uscito dal tuo profilo artigiano.', 'info')
    return redirect(url_for('artigiani.elenco'))


# ── Verifica email ────────────────────────────────────────────────────────────

@artigiani_auth.route('/verifica-email/<token>')
def verifica_email(token):
    try:
        email = _serializer().loads(token, salt=SALT_VERIFY, max_age=86400)
    except SignatureExpired:
        flash('Il link di conferma è scaduto (valido 24h). '
              'Registrati di nuovo.', 'danger')
        return redirect(url_for('artigiani_auth.registrati'))
    except BadSignature:
        flash('Link di conferma non valido.', 'danger')
        return redirect(url_for('artigiani_auth.login'))

    hobbista = HobbistaAccount.query.filter_by(email=email).first()
    if not hobbista:
        flash('Account non trovato.', 'danger')
        return redirect(url_for('artigiani_auth.registrati'))

    if hobbista.email_verificata:
        flash('Email già confermata. Puoi accedere.', 'info')
        return redirect(url_for('artigiani_auth.login'))

    hobbista.email_verificata = True
    db.session.commit()

    flash('Email confermata! Ora puoi accedere al tuo profilo.', 'success')
    return redirect(url_for('artigiani_auth.login'))


# ── Google OAuth ─────────────────────────────────────────────────────────────
# TODO: Integrare Google OAuth con Authlib in step successivo.
# Aggiungere Authlib a requirements.txt, configurare GOOGLE_CLIENT_ID e
# GOOGLE_CLIENT_SECRET in .env, implementare /artigiani/auth/google e
# /artigiani/auth/google/callback seguendo il pattern Authorization Code.
