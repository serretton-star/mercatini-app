from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user, logout_user
from app import db, bcrypt
from app.models import Mercatino
from app.account import account
from app.account.forms import ProfiloForm, CambiaPasswordForm


@account.route('/')
@login_required
def profilo():
    from app.models.mercatino import Preferito, Alert, Categoria as _Cat
    miei = (Mercatino.query.filter_by(organizzatore_id=current_user.id)
            .order_by(Mercatino.created_at.desc()).all())
    preferiti = (Preferito.query.filter_by(user_id=current_user.id)
                 .order_by(Preferito.created_at.desc()).all())
    alerts = Alert.query.filter_by(user_id=current_user.id, attivo=True).all()
    categorie = _Cat.query.order_by(_Cat.nome).all()
    profilo_form = ProfiloForm(obj=current_user)
    pw_form = CambiaPasswordForm()
    return render_template('account/profilo.html',
                           miei=miei, preferiti=preferiti, alerts=alerts,
                           categorie=categorie,
                           profilo_form=profilo_form, pw_form=pw_form)


@account.route('/modifica-profilo', methods=['POST'])
@login_required
def modifica_profilo():
    form = ProfiloForm()
    if form.validate_on_submit():
        current_user.nome = form.nome.data
        current_user.cognome = form.cognome.data
        current_user.bio = form.bio.data or None
        current_user.categoria_prodotti = form.categoria_prodotti.data or None
        current_user.fascia_prezzo = form.fascia_prezzo.data or None
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
        if not bcrypt.check_password_hash(current_user.password_hash, form.password_attuale.data):
            flash('Password attuale non corretta.', 'danger')
        else:
            current_user.password_hash = bcrypt.generate_password_hash(
                form.nuova_password.data, rounds=12).decode('utf-8')
            db.session.commit()
            flash('Password cambiata con successo.', 'success')
    else:
        for field, errors in form.errors.items():
            for e in errors:
                flash(e, 'danger')
    return redirect(url_for('account.profilo'))


@account.route('/notifiche', methods=['POST'])
@login_required
def aggiorna_notifiche():
    """Toggle preferenze notifiche email."""
    current_user.notifiche_email = 'notifiche_email' in request.form
    db.session.commit()
    if current_user.notifiche_email:
        flash('Notifiche attivate. Riceverai email sui mercatini della tua provincia.', 'success')
    else:
        flash('Notifiche disattivate.', 'info')
    return redirect(url_for('account.profilo'))


# ------------------------------------------------------------------
# Preferiti
# ------------------------------------------------------------------
@account.route('/preferiti/toggle/<int:mercatino_id>', methods=['POST'])
@login_required
def toggle_preferito(mercatino_id):
    from app.models.mercatino import Preferito, Mercatino
    Mercatino.query.get_or_404(mercatino_id)
    pref = Preferito.query.filter_by(
        user_id=current_user.id, mercatino_id=mercatino_id).first()
    if pref:
        db.session.delete(pref)
        db.session.commit()
        return jsonify({'salvato': False})
    else:
        db.session.add(Preferito(user_id=current_user.id, mercatino_id=mercatino_id))
        db.session.commit()
        return jsonify({'salvato': True})


# ------------------------------------------------------------------
# Alert personalizzati
# ------------------------------------------------------------------
@account.route('/alert/crea', methods=['POST'])
@login_required
def crea_alert():
    from app.models.mercatino import Alert
    parole = (request.form.get('parole_chiave') or '').strip()
    provincia = (request.form.get('provincia') or '').strip().upper()[:5]
    cat_id = request.form.get('categoria_id', type=int) or None
    if not parole and not provincia and not cat_id:
        flash("Specifica almeno un criterio per l'alert.", "warning")
        return redirect(url_for('account.profilo') + '#alert')
    # max 5 alert per utente
    n = Alert.query.filter_by(user_id=current_user.id, attivo=True).count()
    if n >= 5:
        flash('Puoi avere al massimo 5 alert attivi.', 'warning')
        return redirect(url_for('account.profilo') + '#alert')
    a = Alert(user_id=current_user.id, parole_chiave=parole or None,
              provincia=provincia or None, categoria_id=cat_id)
    db.session.add(a)
    db.session.commit()
    flash('Alert creato! Ti avviseremo via email.', 'success')
    return redirect(url_for('account.profilo') + '#alert')


@account.route('/alert/<int:alert_id>/elimina', methods=['POST'])
@login_required
def elimina_alert(alert_id):
    from app.models.mercatino import Alert
    a = Alert.query.filter_by(id=alert_id, user_id=current_user.id).first_or_404()
    db.session.delete(a)
    db.session.commit()
    flash('Alert eliminato.', 'info')
    return redirect(url_for('account.profilo') + '#alert')
