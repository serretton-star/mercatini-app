import logging
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
        )
        db.session.add(user)
        db.session.commit()
        flash('Registrazione completata! Ora puoi accedere.', 'success')
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
            login_user(user, remember=form.remember_me.data)
            next_page = request.args.get('next')
            flash(f'Benvenuto, {user.nome}!', 'success')
            return redirect(next_page or url_for('main.index'))
        flash('Email o password non corretti.', 'danger')
    return render_template('auth/login.html', form=form)


@auth.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Hai effettuato il logout.', 'info')
    return redirect(url_for('main.index'))


# ------------------------------------------------------------------
# Password Reset
# ------------------------------------------------------------------
@auth.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))
    form = ForgotPasswordForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data.lower().strip()).first()
        # Sempre stesso messaggio per evitare user enumeration
        flash('Se l\'email è registrata, riceverai un link per reimpostare la password.', 'info')
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


def _invia_email_reset(user, reset_url):
    """Invia email di reset. Se SMTP non configurato, logga il link."""
    if current_app.config.get('MAIL_SUPPRESS_SEND'):
        log.warning(f'[PASSWORD RESET] Link per {user.email}: {reset_url}')
        return
    try:
        msg = Message(
            subject='Reimposta la tua password — Mercatini App',
            recipients=[user.email],
            body=(
                f'Ciao {user.nome},\n\n'
                f'Hai richiesto il reset della password. Clicca sul link qui sotto '
                f'(valido 1 ora):\n\n{reset_url}\n\n'
                f'Se non hai fatto questa richiesta, ignora questa email.\n\n'
                f'— Il team di Mercatini App'
            ),
        )
        mail.send(msg)
    except Exception as e:
        log.error(f'Errore invio email reset: {e}')
