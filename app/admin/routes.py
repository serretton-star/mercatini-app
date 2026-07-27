from functools import wraps
from flask import render_template, redirect, url_for, flash, abort, request
from flask_login import login_required, current_user
from app import db
from app.models import User, Mercatino, Categoria
from app.admin import admin


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return decorated


@admin.route('/')
@login_required
@admin_required
def dashboard():
    stats = {
        'utenti': User.query.count(),
        'mercatini': Mercatino.query.count(),
        'pubblicati': Mercatino.query.filter_by(pubblicato=True).count(),
        'bozze': Mercatino.query.filter_by(pubblicato=False).count(),
    }
    mercatini = (
        Mercatino.query
        .order_by(Mercatino.created_at.desc())
        .limit(50)
        .all()
    )
    utenti = User.query.order_by(User.created_at.desc()).all()
    categorie = Categoria.query.order_by(Categoria.nome).all()
    return render_template(
        'admin/dashboard.html',
        stats=stats,
        mercatini=mercatini,
        utenti=utenti,
        categorie=categorie,
    )


@admin.route('/mercatino/<int:id>/toggle-pubblicato', methods=['POST'])
@login_required
@admin_required
def toggle_pubblicato(id):
    m = Mercatino.query.get_or_404(id)
    m.pubblicato = not m.pubblicato
    db.session.commit()
    stato = 'pubblicato' if m.pubblicato else 'messo in bozza'
    flash(f'"{m.titolo}" {stato}.', 'success')
    return redirect(url_for('admin.dashboard'))


@admin.route('/utente/<int:id>/toggle-attivo', methods=['POST'])
@login_required
@admin_required
def toggle_utente(id):
    u = User.query.get_or_404(id)
    if u.id == current_user.id:
        flash('Non puoi disattivare te stesso.', 'warning')
        return redirect(url_for('admin.dashboard'))
    u.is_active = not u.is_active
    db.session.commit()
    stato = 'attivato' if u.is_active else 'disattivato'
    flash(f'{u.nome_completo} {stato}.', 'success')
    return redirect(url_for('admin.dashboard'))


@admin.route('/utente/<int:id>/promuovi-admin', methods=['POST'])
@login_required
@admin_required
def promuovi_admin(id):
    u = User.query.get_or_404(id)
    u.ruolo = 'admin' if u.ruolo != 'admin' else 'espositore'
    db.session.commit()
    flash(f'{u.nome_completo}: ruolo impostato a {u.ruolo}.', 'success')
    return redirect(url_for('admin.dashboard'))


# ------------------------------------------------------------------
# Gestione Categorie
# ------------------------------------------------------------------
@admin.route('/categoria/crea', methods=['POST'])
@login_required
@admin_required
def crea_categoria():
    nome = request.form.get('nome', '').strip()
    if not nome:
        flash('Il nome della categoria è obbligatorio.', 'danger')
        return redirect(url_for('admin.dashboard'))
    from slugify import slugify
    slug = slugify(nome)
    if Categoria.query.filter_by(slug=slug).first():
        flash(f'La categoria "{nome}" esiste già.', 'warning')
        return redirect(url_for('admin.dashboard'))
    db.session.add(Categoria(nome))
    db.session.commit()
    flash(f'Categoria "{nome}" creata.', 'success')
    return redirect(url_for('admin.dashboard'))


@admin.route('/categoria/<int:id>/elimina', methods=['POST'])
@login_required
@admin_required
def elimina_categoria(id):
    c = Categoria.query.get_or_404(id)
    if c.mercatini.count() > 0:
        flash(f'Impossibile eliminare "{c.nome}": ha mercatini associati.', 'warning')
        return redirect(url_for('admin.dashboard'))
    nome = c.nome
    db.session.delete(c)
    db.session.commit()
    flash(f'Categoria "{nome}" eliminata.', 'success')
    return redirect(url_for('admin.dashboard'))
