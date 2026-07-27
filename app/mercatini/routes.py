from datetime import date
from flask import render_template, redirect, url_for, flash, request, abort
from flask_login import login_required, current_user
from sqlalchemy import or_
from app import db
from app.models import Mercatino, Categoria
from app.mercatini import mercatini
from app.mercatini.forms import MercatinoForm


def _populate_categorie(form):
    """Popola le scelte del campo categorie dal DB."""
    categorie = Categoria.query.order_by(Categoria.nome).all()
    form.categorie.choices = [(c.id, c.nome) for c in categorie]
    return categorie


# ------------------------------------------------------------------
# Lista mercatini
# ------------------------------------------------------------------
@mercatini.route('/')
def index():
    page = request.args.get('page', 1, type=int)
    q = request.args.get('q', '', type=str).strip()
    regione = request.args.get('regione', '', type=str).strip()
    citta = request.args.get('citta', '', type=str).strip()
    cat_id = request.args.get('categoria', 0, type=int)

    query = Mercatino.query.filter_by(pubblicato=True)

    if q:
        pattern = f'%{q}%'
        query = query.filter(or_(
            Mercatino.titolo.ilike(pattern),
            Mercatino.citta.ilike(pattern),
            Mercatino.regione.ilike(pattern),
            Mercatino.descrizione.ilike(pattern),
        ))
    if regione:
        query = query.filter(Mercatino.regione.ilike(f'%{regione}%'))
    if citta:
        query = query.filter(Mercatino.citta.ilike(f'%{citta}%'))
    if cat_id:
        query = query.join(Mercatino.categorie).filter(Categoria.id == cat_id)

    query = query.order_by(Mercatino.data_inizio.asc())
    pagination = query.paginate(page=page, per_page=12, error_out=False)

    categorie = Categoria.query.order_by(Categoria.nome).all()
    return render_template(
        'mercatini/index.html',
        mercatini=pagination.items,
        pagination=pagination,
        categorie=categorie,
        filtro_q=q,
        filtro_regione=regione,
        filtro_citta=citta,
        filtro_cat=cat_id,
        totale_risultati=pagination.total,
    )


# ------------------------------------------------------------------
# Dettaglio mercatino
# ------------------------------------------------------------------
@mercatini.route('/<int:id>')
def dettaglio(id):
    m = Mercatino.query.get_or_404(id)
    if not m.pubblicato and (
        not current_user.is_authenticated or
        (current_user.id != m.organizzatore_id and not current_user.is_admin)
    ):
        abort(404)
    return render_template('mercatini/dettaglio.html', mercatino=m)


# ------------------------------------------------------------------
# Crea nuovo mercatino
# ------------------------------------------------------------------
@mercatini.route('/nuovo', methods=['GET', 'POST'])
@login_required
def nuovo():
    form = MercatinoForm()
    _populate_categorie(form)

    if form.validate_on_submit():
        m = Mercatino(
            titolo=form.titolo.data,
            descrizione=form.descrizione.data,
            citta=form.citta.data,
            regione=form.regione.data,
            provincia=form.provincia.data or None,
            indirizzo=form.indirizzo.data or None,
            data_inizio=form.data_inizio.data,
            data_fine=form.data_fine.data,
            orario=form.orario.data or None,
            sito_web=form.sito_web.data or None,
            telefono=form.telefono.data or None,
            email_contatto=form.email_contatto.data or None,
            ingresso_gratuito=form.ingresso_gratuito.data,
            prezzo_ingresso=form.prezzo_ingresso.data if not form.ingresso_gratuito.data else None,
            numero_espositori=form.numero_espositori.data or None,
            pubblicato=form.pubblicato.data,
            organizzatore_id=current_user.id,
        )
        # Categorie
        if form.categorie.data:
            cats = Categoria.query.filter(Categoria.id.in_(form.categorie.data)).all()
            m.categorie = cats
        db.session.add(m)
        db.session.commit()
        flash('Mercatino inserito con successo!', 'success')
        return redirect(url_for('mercatini.dettaglio', id=m.id))

    return render_template('mercatini/form.html', form=form, titolo_pagina='Nuovo mercatino')


# ------------------------------------------------------------------
# Modifica mercatino
# ------------------------------------------------------------------
@mercatini.route('/<int:id>/modifica', methods=['GET', 'POST'])
@login_required
def modifica(id):
    m = Mercatino.query.get_or_404(id)
    if current_user.id != m.organizzatore_id and not current_user.is_admin:
        abort(403)

    form = MercatinoForm(obj=m)
    _populate_categorie(form)

    if request.method == 'GET':
        form.categorie.data = [c.id for c in m.categorie]

    if form.validate_on_submit():
        m.titolo = form.titolo.data
        m.descrizione = form.descrizione.data
        m.citta = form.citta.data
        m.regione = form.regione.data
        m.provincia = form.provincia.data or None
        m.indirizzo = form.indirizzo.data or None
        m.data_inizio = form.data_inizio.data
        m.data_fine = form.data_fine.data
        m.orario = form.orario.data or None
        m.sito_web = form.sito_web.data or None
        m.telefono = form.telefono.data or None
        m.email_contatto = form.email_contatto.data or None
        m.ingresso_gratuito = form.ingresso_gratuito.data
        m.prezzo_ingresso = form.prezzo_ingresso.data if not form.ingresso_gratuito.data else None
        m.numero_espositori = form.numero_espositori.data or None
        m.pubblicato = form.pubblicato.data
        if form.categorie.data:
            cats = Categoria.query.filter(Categoria.id.in_(form.categorie.data)).all()
            m.categorie = cats
        else:
            m.categorie = []
        db.session.commit()
        flash('Mercatino aggiornato con successo!', 'success')
        return redirect(url_for('mercatini.dettaglio', id=m.id))

    return render_template('mercatini/form.html', form=form, mercatino=m,
                           titolo_pagina='Modifica mercatino')


# ------------------------------------------------------------------
# Elimina mercatino
# ------------------------------------------------------------------
@mercatini.route('/<int:id>/elimina', methods=['POST'])
@login_required
def elimina(id):
    m = Mercatino.query.get_or_404(id)
    if current_user.id != m.organizzatore_id and not current_user.is_admin:
        abort(403)
    db.session.delete(m)
    db.session.commit()
    flash('Mercatino eliminato.', 'info')
    return redirect(url_for('mercatini.index'))


# ------------------------------------------------------------------
# AI: estrai dati mercatino da testo o immagine
# ------------------------------------------------------------------
@mercatini.route('/ai-estrai', methods=['POST'])
@login_required
def ai_estrai():
    """Usa Claude per estrarre dati strutturati da testo libero o screenshot."""
    import anthropic as _ant
    import json as _json
    from flask import current_app, jsonify

    api_key = current_app.config.get('ANTHROPIC_API_KEY')
    if not api_key:
        return jsonify({'error': 'AI non disponibile'}), 503

    data = request.get_json(silent=True) or {}
    testo      = (data.get('testo') or '').strip()
    img_b64    = (data.get('immagine') or '').strip()
    img_tipo   = (data.get('tipo') or 'image/jpeg').strip()

    if not testo and not img_b64:
        return jsonify({'error': 'Inserisci testo o immagine'}), 400

    SYSTEM = (
        "Sei un assistente specializzato in mercatini italiani. "
        "Analizza il testo/immagine e restituisci SOLO un oggetto JSON valido "
        "(nessun altro testo, nessun markdown) con questi campi (null se mancante):\n"
        '{"titolo":null,"descrizione":null,"citta":null,"regione":null,'
        '"provincia":null,"indirizzo":null,"data_inizio":null,"data_fine":null,'
        '"orario":null,"ingresso_gratuito":true,"prezzo_ingresso":null,'
        '"numero_espositori":null,"sito_web":null,"telefono":null,"email_contatto":null}\n'
        "data_inizio e data_fine in formato YYYY-MM-DD. "
        "regione: nome completo (es. Lombardia). provincia: sigla 2 lettere (es. MI)."
    )

    content = []
    if img_b64:
        content.append({
            'type': 'image',
            'source': {'type': 'base64', 'media_type': img_tipo, 'data': img_b64}
        })
    content.append({'type': 'text',
                    'text': testo if testo else "Estrai le info dall'immagine."})

    try:
        model = current_app.config.get('ANTHROPIC_MODEL', 'claude-haiku-4-5-20251001')
        client = _ant.Anthropic(api_key=api_key)
        resp = client.messages.create(
            model=model, max_tokens=1024, system=SYSTEM,
            messages=[{'role': 'user', 'content': content}]
        )
        raw = resp.content[0].text.strip()
        if raw.startswith('```'):
            raw = raw.split('```')[1]
            if raw.startswith('json'): raw = raw[4:]
        dati = _json.loads(raw.strip())
        return jsonify({'ok': True, 'dati': dati})
    except (_ant.APIError, _json.JSONDecodeError, Exception) as e:
        return jsonify({'error': str(e)}), 502
