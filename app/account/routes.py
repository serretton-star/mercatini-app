from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app import db, bcrypt
from app.models import Mercatino
from app.account import account
from app.account.forms import ProfiloForm, CambiaPasswordForm


@account.route('/')
@login_required
def profilo():
    miei = (
        Mercatino.query
        .filter_by(organizzatore_id=current_user.id)
        .order_by(Mercatino.created_at.desc())
        .all()
    )
    profilo_form = ProfiloForm(obj=current_user)
    pw_form = CambiaPasswordForm()
    return render_template(
        'account/profilo.html',
        miei=miei,
        profilo_form=profilo_form,
        pw_form=pw_form,
    )


@account.route('/modifica-profilo', methods=['POST'])
@login_required
def modifica_profilo():
    form = ProfiloForm()
    if form.validate_on_submit():
        current_user.nome = form.nome.data
        current_user.cognome = form.cognome.data
        current_user.bio = form.bio.data or None
        db.session.commit()
        flash('Profilo aggiornato.', 'success')
    else:
        for field, errors in form.errors.items():
            for e in errors:
                flash(e, 'danger')
    return redirect(url_for('account.profilo'))


@account.route('/cambia-password', methods=['POST'])
@login_required
def cambia_password():
    form = CambiaPasswordForm()
    if form.validate_on_submit():
        if not bcrypt.check_password_hash(
            current_user.password_hash, form.password_attuale.data
        ):
            flash('Password attuale non corretta.', 'danger')
        else:
            current_user.password_hash = bcrypt.generate_password_hash(
                form.nuova_password.data, rounds=12
            ).decode('utf-8')
            db.session.commit()
            flash('Password cambiata con successo.', 'success')
    else:
        for field, errors in form.errors.items():
            for e in errors:
                flash(e, 'danger')
    return redirect(url_for('account.profilo'))
