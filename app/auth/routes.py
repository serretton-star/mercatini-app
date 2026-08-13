import logging
from datetime import datetime, timezone
from flask import render_template, redirect, url_for, flash, request, current_app
from flask_login import login_user, logout_user, login_required, current_user
from flask_mail import Message

from app import db, bcrypt, limiter, mail
from app.auth import auth
from app.auth.forms import RegistrationForm, LoginForm, ForgotPasswordForm, ResetPasswordForm
from app.models.user import User

log = logging.getLogger(__name__)


@auth.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    form = RegistrationForm()
    if form.validate_on_submit():
        pw_hash = bcrypt.generate_password_hash(form.password.data, rounds=12).decode('utf-8')
        user = User(
            nome=form.nome.data.strip(),
            cognome=form.cognome.data.strip(),
            email=form.email.data.lower().strip(),
            password_hash=pw_hash,
            provincia_residenza=form.provincia_residenza.data or None,
            categoria_prodotti=form.categoria_prodotti.data or None,
            fascia_prezzo=form.fascia_prezzo.data or None,
            notifiche_email=bool(form.notifiche_email.data),
            privacy_accepted=True,
            privacy_accepted_at=datetime.now(timezone.utc),
            email_verified=False,
        )
        # Free 5-day trial for new users
        from datetime import timedelta
        user.subscription_plan = 'trial'
        user.subscription_end  = datetime.now(timezone.utc) + timedelta(days=5)
        token = user.genera_verify_token()
        db.session.add(user)
        db.session.commit()
        verify_url = url_for('auth.conferma_email', token=token, _external=True)
        _invia_email_verifica(user, verify_url)
        flash('Registrazione completata! Controlla la tua email per confermare l\'account.', 'success')
        return redirect(url_for('auth.login'))
    return render_template('auth/register.html', form=form)


@auth.route('/login', methods=['GET', 'POST'])
@limiter.limit('5 per minute')
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data.lower().strip()).first()
        if user and user.is_active and bcrypt.check_password_hash(
            user.password_hash, form.password.data
        ):
            if not user.email_verified:
                flash('Devi prima confermare la tua email. '
                      '<a href="' + url_for('auth.reinvia_conferma', email=user.email) + '">'
                      'Reinvia email di conferma</a>.', 'warning')
                return render_template('auth/login.html', form=form)
            login_user(user, remember=form.remember_me.data)
            next_page = request.args.get('next')
            flash(f'Benvenuto, {user.nome}!', 'success')
            return redirect(next_page or url_for('main.index'))
        flash('Email o password non corretti.', 'danger')
    return render_template('auth/login.html', form=form)


@auth.route('/conferma-email/<token>')
def conferma_email(token):
    user = User.query.filter_by(email_verify_token=token).first()
    if not user:
        flash('Link di conferma non valido o già utilizzato.', 'danger')
        return redirect(url_for('auth.login'))
    user.conferma_email()
    db.session.commit()
    login_user(user)
    flash(f'Email confermata! Benvenuto su mercatini.blog, {user.nome}!', 'success')
    return redirect(url_for('main.index'))


@auth.route('/reinvia-conferma')
def reinvia_conferma():
    email = request.args.get('email', '').lower().strip()
    user = User.query.filter_by(email=email).first()
    if user and not user.email_verified:
        token = user.genera_verify_token()
        db.session.commit()
        verify_url = url_for('auth.conferma_email', token=token, _external=True)
        _invia_email_verifica(user, verify_url)
    flash('Se l\'email è registrata e non ancora confermata, ti abbiamo inviato un nuovo link.', 'info')
    return redirect(url_for('auth.login'))


@auth.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Hai effettuato il logout.', 'info')
    return redirect(url_for('main.index'))


@auth.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    form = ForgotPasswordForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data.lower().strip()).first()
        flash("Se l'email e' registrata, riceverai un link per reimpostare la password.", 'info')
        if user:
            token = user.genera_reset_token(expires_hours=1)
            db.session.commit()
            reset_url = url_for('auth.reset_password', token=token, _external=True)
            _invia_email_reset(user, reset_url)
        return redirect(url_for('auth.login'))
    return render_template('auth/forgot_password.html', form=form)


@auth.route('/reset/<token>', methods=['GET', 'POST'])
def reset_password(token):
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    user = User.query.filter_by(reset_token=token).first()
    if not user or not user.reset_token_valido():
        flash('Link non valido o scaduto. Richiedi un nuovo reset.', 'danger')
        return redirect(url_for('auth.forgot_password'))
    form = ResetPasswordForm()
    if form.validate_on_submit():
        user.password_hash = bcrypt.generate_password_hash(
            form.password.data, rounds=12
        ).decode('utf-8')
        user.cancella_reset_token()
        db.session.commit()
        flash('Password reimpostata! Ora puoi accedere.', 'success')
        return redirect(url_for('auth.login'))
    return render_template('auth/reset_password.html', form=form, token=token)


def _invia_email_verifica(user, verify_url):
    if current_app.config.get('MAIL_SUPPRESS_SEND'):
        log.warning(f'[EMAIL VERIFICA] Link per {user.email}: {verify_url}')
        return
    try:
        msg = Message(
            subject='Conferma la tua email - mercatini.blog',
            recipients=[user.email],
            body=(
                f'Ciao {user.nome},\n\n'
                f'Grazie per esserti registrato su mercatini.blog!\n\n'
                f'Clicca sul link qui sotto per confermare la tua email:\n\n'
                f'{verify_url}\n\n'
                f'Se non hai creato un account, ignora questa email.\n\n'
                f'Il team di mercatini.blog'
            ),
        )
        mail.send(msg)
    except Exception as e:
        log.error(f'Errore invio email verifica a {user.email}: {e}')


def _invia_email_reset(user, reset_url):
    if current_app.config.get('MAIL_SUPPRESS_SEND'):
        log.warning(f'[PASSWORD RESET] Link per {user.email}: {reset_url}')
        return
    try:
        msg = Message(
            subject='Reimposta la tua password - mercatini.blog',
            recipients=[user.email],
            body=(
                f'Ciao {user.nome},\n\n'
                f'Hai richiesto il reset della password. Clicca sul link (valido 1 ora):\n\n'
                f'{reset_url}\n\n'
                f'Se non hai fatto questa richiesta, ignora questa email.\n\n'
                f'Il team di mercatini.blog'
            ),
        )
        mail.send(msg)
    except Exception as e:
        log.error(f'Errore invio email reset a {user.email}: {e}')


def notifica_nuovi_eventi(mercatino):
    """Invia email agli utenti della provincia con notifiche_email=True e privacy_accepted=True."""
    from app.models.user import User as _User
    prov = getattr(mercatino, 'provincia', None)
    if not prov:
        return
    try:
        utenti = _User.query.filter_by(
            provincia_residenza=prov,
            notifiche_email=True,
            privacy_accepted=True,
            is_active=True,
        ).all()
        if not utenti:
            return
        url = f'https://mercatini.blog/mercatini/{mercatino.id}'
        d_ini = mercatino.data_inizio.strftime('%d/%m/%Y') if mercatino.data_inizio else '?'
        d_fin = mercatino.data_fine.strftime('%d/%m/%Y') if mercatino.data_fine else '?'
        for u in utenti:
            try:
                msg = Message(
                    subject=f'Nuovo mercatino nella tua provincia ({prov}) - Mercatini.blog',
                    recipients=[u.email],
                    body=(
                        f'Ciao {u.nome},\n\n'
                        f'E stato pubblicato un nuovo mercatino nella tua provincia ({prov}):\n\n'
                        f'  {mercatino.titolo}\n'
                        f'  {mercatino.citta or ""}, {mercatino.regione or ""}\n'
                        f'  Date: {d_ini} - {d_fin}\n\n'
                        f'Scopri i dettagli: {url}\n\n'
                        f'Per disattivare le notifiche: Mercatini.blog > Il mio account > Notifiche\n\n'
                        f'-- Il team di Mercatini.blog'
                    ),
                )
                mail.send(msg)
            except Exception as ex:
                log.error(f'Notifica email fallita per {u.email}: {ex}')
    except Exception as ex:
        log.error(f'Errore notifica provincia: {ex}')
