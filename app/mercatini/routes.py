from datetime import date
from flask import render_template, redirect, url_for, flash, request, abort, jsonify
from flask_login import login_required, current_user
from sqlalchemy import or_, func as _sqlfunc
from app import db, csrf
from app.auth.routes import notifica_nuovi_eventi
from app.models import Mercatino, Categoria
from app.mercatini import mercatini
from app.mercatini.forms import MercatinoForm
from app.models.mercatino import RICORRENZA_SCELTE


# ------------------------------------------------------------------
# Helper: meteo OpenWeatherMap (solo eventi entro 7 giorni)
# ------------------------------------------------------------------
def _get_meteo(citta, api_key, data_inizio, data_fine):
    """Ritorna lista di {data, icona, temp, desc} per i giorni dell'evento (max 5gg)."""
    if not api_key or not citta:
        return []
    from datetime import date as _date, timedelta
    oggi = _date.today()
    limite = oggi + timedelta(days=7)
    if data_inizio > limite:
        return []
    try:
        import requests as _req
        url = 'https://api.openweathermap.org/data/2.5/forecast'
        resp = _req.get(url, params={
            'q': f'{citta},IT', 'appid': api_key,
            'units': 'metric', 'lang': 'it', 'cnt': 40
        }, timeout=4)
        if resp.status_code != 200:
            return []
        data = resp.json()
        ICONS = {
            '01': '☀️', '02': '🌤', '03': '☁️', '04': '☁️',
            '09': '🌧', '10': '🌦', '11': '⛈', '13': '❄️', '50': '🌫'
        }
        giorni_visti = set()
        risultati = []
        for item in data.get('list', []):
            dt = _date.fromtimestamp(item['dt'])
            if dt < oggi or dt > min(data_fine, limite):
                continue
            giorno_str = dt.strftime('%d/%m')
            if giorno_str in giorni_visti:
                continue
            giorni_visti.add(giorno_str)
            cod = item['weather'][0]['icon'][:2]
            risultati.append({
                'data': dt.strftime('%a %d/%m'),
                'icona': ICONS.get(cod, '🌡'),
                'temp': round(item['main']['temp']),
                'desc': item['weather'][0]['description'].capitalize(),
            })
            if len(risultati) >= 5:
                break
        return risultati
    except Exception:
        return []


def _populate_categorie(form):
    """Popola le scelte del campo categorie dal DB."""
    categorie = Categoria.query.order_by(Categoria.nome).all()
    form.categorie.choices = [(c.id, c.nome) for c in categorie]
    return categorie


# ------------------------------------------------------------------
# ------------------------------------------------------------------
# Lista mercatini (pubblica, stile directory)
# ------------------------------------------------------------------
@mercatini.route('/')
def index():
    import calendar as _cal, math as _math
    from datetime import date as _date_cls

    def _haversine(lat1, lon1, lat2, lon2):
        R = 6371.0
        ph1, ph2 = _math.radians(lat1), _math.radians(lat2)
        dp = _math.radians(lat2 - lat1)
        dl = _math.radians(lon2 - lon1)
        a = _math.sin(dp/2)**2 + _math.cos(ph1)*_math.cos(ph2)*_math.sin(dl/2)**2
        return round(R * 2 * _math.atan2(_math.sqrt(a), _math.sqrt(1-a)), 1)

    class _FakePag:
        def __init__(self, items, page, per_page, total):
            self.items = items; self.page = page; self.per_page = per_page
            self.total = total
            self.pages = max(1, (total + per_page - 1) // per_page)
            self.has_prev = page > 1; self.has_next = page < self.pages
            self.prev_num = page - 1; self.next_num = page + 1

    oggi = _date_cls.today()
    anno = request.args.get('anno', oggi.year, type=int)
    mese = request.args.get('mese', oggi.month, type=int)
    anno = max(2020, min(2035, anno))
    mese = max(1, min(12, mese))

    page  = request.args.get('page', 1, type=int)
    q     = request.args.get('q', '', type=str).strip()
    regione = request.args.get('regione', '', type=str).strip()
    cat_id  = request.args.get('categoria', 0, type=int)
    mostra_tutti = request.args.get('mostra_tutti', '') == '1'

    # Geolocalizzazione
    user_lat = request.args.get('lat', None, type=float)
    user_lon = request.args.get('lon', None, type=float)
    raggio   = request.args.get('raggio', 50, type=int)
    if raggio not in (10, 25, 50, 100):
        raggio = 50

    query = Mercatino.query.filter_by(pubblicato=True)

    if not mostra_tutti:
        first_day = _date_cls(anno, mese, 1)
        last_day  = _date_cls(anno, mese, _cal.monthrange(anno, mese)[1])
        query = query.filter(
            Mercatino.data_inizio <= last_day,
            Mercatino.data_fine   >= first_day
        )

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
    if cat_id:
        query = query.join(Mercatino.categorie).filter(Categoria.id == cat_id)

    # ----------------------------------------------------------------
    # Deduplicazione eventi ricorrenti: per ogni (titolo, città, organizzatore)
    # mostra solo la prima occorrenza attiva/futura (MIN id).
    # Risolve il problema dei mercatini settimanali inseriti come righe separate.
    # ----------------------------------------------------------------
    dedup_sq = (
        db.session.query(_sqlfunc.min(Mercatino.id).label('repr_id'))
        .filter(
            Mercatino.pubblicato == True,
            Mercatino.data_fine >= oggi,
        )
        .group_by(
            _sqlfunc.lower(Mercatino.titolo),
            _sqlfunc.lower(db.func.coalesce(Mercatino.citta, '')),
            Mercatino.organizzatore_id,
        )
        .subquery('dedup_sq')
    )
    query = query.join(dedup_sq, Mercatino.id == dedup_sq.c.repr_id)

    distanze = {}
    if user_lat and user_lon:
        # Filtra e ordina per distanza (fetch all, poi pagina in Python)
        tutti = query.order_by(Mercatino.data_inizio.asc()).all()
        vicini = []
        for m in tutti:
            if m.lat and m.lon:
                d = _haversine(user_lat, user_lon, float(m.lat), float(m.lon))
                if d <= raggio:
                    distanze[m.id] = d
                    vicini.append(m)
        vicini.sort(key=lambda m: distanze.get(m.id, 9999))
        per_page = 15
        total = len(vicini)
        start = (page - 1) * per_page
        pagination = _FakePag(vicini[start:start+per_page], page, per_page, total)
    else:
        query = query.order_by(Mercatino.data_inizio.asc())
        pagination = query.paginate(page=page, per_page=15, error_out=False)

    categorie = Categoria.query.order_by(Categoria.nome).all()

    MESI_IT = ['Gennaio','Febbraio','Marzo','Aprile','Maggio','Giugno',
               'Luglio','Agosto','Settembre','Ottobre','Novembre','Dicembre']
    MESI_SHORT = ['GEN','FEB','MAR','APR','MAG','GIU',
                  'LUG','AGO','SET','OTT','NOV','DIC']

    prev_mese = mese - 1 if mese > 1 else 12
    prev_anno = anno if mese > 1 else anno - 1
    next_mese = mese + 1 if mese < 12 else 1
    next_anno = anno if mese < 12 else anno + 1

    return render_template(
        'mercatini/index.html',
        mercatini=pagination.items,
        pagination=pagination,
        categorie=categorie,
        filtro_q=q,
        filtro_regione=regione,
        filtro_cat=cat_id,
        mostra_tutti=mostra_tutti,
        anno=anno, mese=mese,
        nome_mese=MESI_IT[mese-1],
        mesi_short=MESI_SHORT,
        prev_mese=prev_mese, prev_anno=prev_anno,
        next_mese=next_mese, next_anno=next_anno,
        totale_risultati=pagination.total,
        user_lat=user_lat, user_lon=user_lon, raggio=raggio,
        distanze=distanze,
    )


@mercatini.route('/<int:id>')
def dettaglio(id):
    m = Mercatino.query.get_or_404(id)
    if not m.pubblicato and (
        not current_user.is_authenticated or
        (current_user.id != m.organizzatore_id and not current_user.is_admin)
    ):
        abort(404)

    from app.models.mercatino import Preferito, Recensione
    from flask import current_app
    is_preferito = False
    user_recensione = None
    if current_user.is_authenticated:
        is_preferito = Preferito.query.filter_by(
            user_id=current_user.id, mercatino_id=m.id).first() is not None
        user_recensione = Recensione.query.filter_by(
            user_id=current_user.id, mercatino_id=m.id).first()

    api_key = current_app.config.get('OPENWEATHER_API_KEY', '')
    meteo = _get_meteo(m.citta, api_key, m.data_inizio, m.data_fine)

    return render_template('mercatini/dettaglio.html', mercatino=m,
                           is_preferito=is_preferito,
                           user_recensione=user_recensione,
                           meteo=meteo)


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
            ingresso_gratuito=True,
            numero_espositori=form.numero_espositori.data or None,
            ricorrenza=form.ricorrenza.data or 'nessuna',
            data_fine_ricorrenza=form.data_fine_ricorrenza.data or None,
            pubblicato=not form.pubblicato.data,
            organizzatore_id=current_user.id,
        )
        # Categorie
        if form.categorie.data:
            cats = Categoria.query.filter(Categoria.id.in_(form.categorie.data)).all()
            m.categorie = cats
        db.session.add(m)
        db.session.commit()
        if m.pubblicato:
            try: notifica_nuovi_eventi(m)
            except Exception: pass
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
        form.pubblicato.data = not m.pubblicato  # checkbox = bozza

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
        m.ingresso_gratuito = True
        m.numero_espositori = form.numero_espositori.data or None
        m.ricorrenza = form.ricorrenza.data or 'nessuna'
        m.data_fine_ricorrenza = form.data_fine_ricorrenza.data or None
        m.pubblicato = not form.pubblicato.data
        if form.categorie.data:
            cats = Categoria.query.filter(Categoria.id.in_(form.categorie.data)).all()
            m.categorie = cats
        else:
            m.categorie = []
        db.session.commit()
        if m.pubblicato:
            try: notifica_nuovi_eventi(m)
            except Exception: pass
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
    import anthropic as _ant
    import json as _json
    from flask import current_app, jsonify
    from datetime import date as _date

    api_key = current_app.config.get('ANTHROPIC_API_KEY')
    if not api_key:
        return jsonify({'error': 'AI non disponibile'}), 503

    data = request.get_json(silent=True) or {}
    testo = (data.get('testo') or '').strip()
    img_b64 = (data.get('immagine') or '').strip()
    img_tipo = (data.get('tipo') or 'image/jpeg').strip()

    if not testo and not img_b64:
        return jsonify({'error': 'Inserisci testo o immagine'}), 400

    _anno = _date.today().year
    CAMPO = '{"titolo":null,"descrizione":null,"citta":null,"regione":null,"provincia":null,"indirizzo":null,"data_inizio":null,"data_fine":null,"orario":null,"ingresso_gratuito":true,"numero_espositori":null,"sito_web":null,"telefono":null,"email_contatto":null}'

    SYSTEM = (
        "Sei un assistente specializzato in mercatini italiani. "
        "Analizza il testo/immagine e identifica TUTTI gli eventi distinti presenti. "
        "Restituisci SOLO un oggetto JSON valido (nessun altro testo, nessun markdown) con questa struttura:\n"
        '{"eventi":[...]}\n'
        "Ogni elemento dell'array 'eventi' rappresenta un evento o un periodo di date distinto "
        "e ha questi campi (null se mancante):\n"
        f"{CAMPO}\n"
        "REGOLE IMPORTANTI:\n"
        "- Se il testo parla di un solo evento: array con 1 elemento.\n"
        "- Se ci sono piu' eventi distinti (organizzatori, luoghi o date diverse): un elemento per ciascuno.\n"
        "- Se uno stesso evento ha piu' periodi di date (es. settimana 17-23 ago, poi 24-30 ago): "
        "  crea un elemento separato per ogni periodo, con stesso titolo/luogo ma date diverse.\n"
        "- Date in formato YYYY-MM-DD. "
        f"Anno corrente: {_anno}. Se manca l'anno usa {_anno}. "
        "Se la data e' passata ma l'evento e' futuro usa l'anno successivo.\n"
        "- regione e provincia: OBBLIGATORI. Usa la tua conoscenza geografica italiana per dedurli SEMPRE dalla citta, anche se non menzionati nel testo. Esempi: Milano->Lombardia/MI, Roma->Lazio/RM, Firenze->Toscana/FI, Napoli->Campania/NA, Torino->Piemonte/TO, Bologna->Emilia-Romagna/BO, Venezia->Veneto/VE, Palermo->Sicilia/PA, Genova->Liguria/GE, Bari->Puglia/BA, Trento->Trentino-Alto Adige/TN. regione: nome completo. provincia: sigla 2 lettere maiuscole.\n"
        "- Max 8 eventi. Descrizione: max 80 caratteri, solo info essenziali."
    )

    content = []
    if img_b64:
        content.append({'type': 'image', 'source': {'type': 'base64', 'media_type': img_tipo, 'data': img_b64}})
    content.append({'type': 'text', 'text': testo if testo else "Estrai le info dall'immagine."})

    try:
        model = current_app.config.get('ANTHROPIC_MODEL', 'claude-haiku-4-5-20251001')
        client = _ant.Anthropic(api_key=api_key)
        resp = client.messages.create(
            model=model, max_tokens=4096, system=SYSTEM,
            messages=[{'role': 'user', 'content': content}]
        )
        raw = resp.content[0].text.strip()
        if raw.startswith('```'):
            raw = raw.split('```')[1]
            if raw.startswith('json'): raw = raw[4:]
        raw = raw.strip()
        try:
            dati = _json.loads(raw)
        except _json.JSONDecodeError:
            for close in ['"}}]}', '"}]}', '"]}', ']}', ']', '}}']:
                try:
                    dati = _json.loads(raw + close)
                    break
                except Exception:
                    continue
            else:
                raise
        # Normalize: accept both {"eventi":[...]} and legacy single-object
        if 'eventi' in dati:
            eventi = dati['eventi']
        else:
            eventi = [dati]
        return jsonify({'ok': True, 'eventi': eventi})
    except (_ant.APIError, _json.JSONDecodeError, Exception) as e:
        return jsonify({'error': str(e)}), 502

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
        '"orario":null,"ingresso_gratuito":true,'
        '"numero_espositori":null,"sito_web":null,"telefono":null,"email_contatto":null}\n'
        "data_inizio e data_fine in formato YYYY-MM-DD. "
        f"Anno corrente: 2026. Se nella data manca l'anno, usa sempre 2026. "
        "Se la data risulta gia' passata ma l'evento e' futuro, usa l'anno successivo. "
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
        raw = raw.strip()
        try:
            dati = _json.loads(raw)
        except _json.JSONDecodeError:
            for close in ['"}}]}', '"}]}', '"]}', ']}', ']', '}}']:
                try:
                    dati = _json.loads(raw + close)
                    break
                except Exception:
                    continue
            else:
                raise
        return jsonify({'ok': True, 'dati': dati})
    except (_ant.APIError, _json.JSONDecodeError, Exception) as e:
        return jsonify({'error': str(e)}), 502


@mercatini.route('/check-duplicato')
@login_required
def check_duplicato():
    from sqlalchemy import or_, and_, func
    from ..models.mercatino import Mercatino
    from datetime import datetime

    titolo = request.args.get('titolo', '').strip()
    citta  = request.args.get('citta', '').strip()
    data_i = request.args.get('data_inizio', '').strip()
    excl   = request.args.get('escludi_id', '').strip()  # per edit: esclude se stesso

    if not titolo and not citta:
        return jsonify({'duplicati': []})

    condizioni = []

    # Titolo simile: ogni parola >= 5 chars
    if titolo:
        parole = [p for p in titolo.split() if len(p) >= 5]
        for parola in parole[:3]:
            condizioni.append(Mercatino.titolo.ilike(f'%{parola}%'))

    # Stessa città + stessa data inizio
    if citta and data_i:
        try:
            d = datetime.strptime(data_i, '%Y-%m-%d').date()
            condizioni.append(and_(
                Mercatino.citta.ilike(f'%{citta}%'),
                Mercatino.data_inizio == d
            ))
        except Exception:
            pass

    if not condizioni:
        return jsonify({'duplicati': []})

    q = Mercatino.query.filter(or_(*condizioni))
    if excl:
        try:
            q = q.filter(Mercatino.id != int(excl))
        except Exception:
            pass

    risultati = q.order_by(Mercatino.id.desc()).limit(5).all()
    duplicati = [{
        'id': m.id,
        'titolo': m.titolo,
        'citta': m.citta or '',
        'data_inizio': m.data_inizio.strftime('%d/%m/%Y') if m.data_inizio else '',
        'data_fine':   m.data_fine.strftime('%d/%m/%Y')   if m.data_fine   else '',
    } for m in risultati]

    return jsonify({'duplicati': duplicati})


@mercatini.route('/lookup-citta')
@login_required
def lookup_citta():
    """Cerca regione e provincia di una citta italiana via Nominatim (OSM)."""
    import urllib.request as _ur
    import urllib.parse as _up
    import json as _json

    # Mappa province italiane sigla -> regione
    PROV_REGIONE = {
        'AG':'Sicilia','AL':'Piemonte','AN':'Marche','AO':'Valle d\'Aosta',
        'AP':'Marche','AQ':'Abruzzo','AR':'Toscana','AT':'Piemonte',
        'AV':'Campania','BA':'Puglia','BG':'Lombardia','BI':'Piemonte',
        'BL':'Veneto','BN':'Campania','BO':'Emilia-Romagna','BR':'Puglia',
        'BS':'Lombardia','BT':'Puglia','BZ':'Trentino-Alto Adige','CA':'Sardegna',
        'CB':'Molise','CE':'Campania','CH':'Abruzzo','CL':'Sicilia',
        'CN':'Piemonte','CO':'Lombardia','CR':'Lombardia','CS':'Calabria',
        'CT':'Sicilia','CZ':'Calabria','EN':'Sicilia','FC':'Emilia-Romagna',
        'FE':'Emilia-Romagna','FG':'Puglia','FI':'Toscana','FM':'Marche',
        'FR':'Lazio','GE':'Liguria','GO':'Friuli-Venezia Giulia','GR':'Toscana',
        'IM':'Liguria','IS':'Molise','KR':'Calabria','LC':'Lombardia',
        'LE':'Puglia','LI':'Toscana','LO':'Lombardia','LT':'Lazio',
        'LU':'Toscana','MB':'Lombardia','MC':'Marche','ME':'Sicilia',
        'MI':'Lombardia','MN':'Lombardia','MO':'Emilia-Romagna','MS':'Toscana',
        'MT':'Basilicata','NA':'Campania','NO':'Piemonte','NU':'Sardegna',
        'OR':'Sardegna','PA':'Sicilia','PC':'Emilia-Romagna','PD':'Veneto',
        'PE':'Abruzzo','PG':'Umbria','PI':'Toscana','PN':'Friuli-Venezia Giulia',
        'PO':'Toscana','PR':'Emilia-Romagna','PT':'Toscana','PU':'Marche',
        'PV':'Lombardia','PZ':'Basilicata','RA':'Emilia-Romagna','RC':'Calabria',
        'RE':'Emilia-Romagna','RG':'Sicilia','RI':'Lazio','RM':'Lazio',
        'RN':'Emilia-Romagna','RO':'Veneto','SA':'Campania','SI':'Toscana',
        'SO':'Lombardia','SP':'Liguria','SR':'Sicilia','SS':'Sardegna',
        'SU':'Sardegna','SV':'Liguria','TA':'Puglia','TE':'Abruzzo',
        'TN':'Trentino-Alto Adige','TO':'Piemonte','TP':'Sicilia','TR':'Umbria',
        'TS':'Friuli-Venezia Giulia','TV':'Veneto','UD':'Friuli-Venezia Giulia',
        'VA':'Lombardia','VB':'Piemonte','VC':'Piemonte','VE':'Veneto',
        'VI':'Veneto','VR':'Veneto','VT':'Lazio','VV':'Calabria',
    }

    citta = request.args.get('citta', '').strip()
    if not citta:
        return jsonify({'trovato': False})

    try:
        q = _up.quote(f'{citta}, Italia')
        url = (f'https://nominatim.openstreetmap.org/search'
               f'?q={q}&format=json&addressdetails=1&limit=1&countrycodes=it')
        req = _ur.Request(url, headers={'User-Agent': 'MercatiniApp/1.0'})
        with _ur.urlopen(req, timeout=5) as resp:
            data = _json.loads(resp.read())

        if not data:
            return jsonify({'trovato': False})

        addr = data[0].get('address', {})
        # Nominatim: state = regione, county/province = provincia
        regione = addr.get('state', '')
        # Cerca sigla provincia nel display_name o nei tag
        provincia_nome = addr.get('county', addr.get('state_district', ''))
        
        # Trova sigla: cerca nel display_name una sigla tra parentesi o nel nome
        sigla = None
        display = data[0].get('display_name', '')
        # Prova match diretto nome provincia
        for sig, reg in PROV_REGIONE.items():
            # Confronta regione
            if regione and reg.lower() in regione.lower():
                pass  # candidato
            # Cerca sigla nel display name tra virgole
            if f', {sig},' in display or display.endswith(f', {sig}'):
                sigla = sig
                regione = PROV_REGIONE.get(sig, regione)
                break
        
        # Fallback: cerca per nome provincia
        if not sigla and provincia_nome:
            pn_clean = provincia_nome.lower()
            pn_clean = pn_clean.replace('provincia di ', '').replace('citta metropolitana di ', '').strip()
            # Mappa nomi comuni provincia
            NOME_SIGLA = {
                'agrigento':'AG','alessandria':'AL','ancona':'AN','aosta':'AO',
                'ascoli piceno':'AP','l\'aquila':'AQ','arezzo':'AR','asti':'AT',
                'avellino':'AV','bari':'BA','bergamo':'BG','biella':'BI',
                'belluno':'BL','benevento':'BN','bologna':'BO','brindisi':'BR',
                'brescia':'BS','barletta-andria-trani':'BT','bolzano':'BZ',
                'cagliari':'CA','campobasso':'CB','caserta':'CE','chieti':'CH',
                'caltanissetta':'CL','cuneo':'CN','como':'CO','cremona':'CR',
                'cosenza':'CS','catania':'CT','catanzaro':'CZ','enna':'EN',
                'forli-cesena':'FC','ferrara':'FE','foggia':'FG','firenze':'FI',
                'fermo':'FM','frosinone':'FR','genova':'GE','gorizia':'GO',
                'grosseto':'GR','imperia':'IM','isernia':'IS','crotone':'KR',
                'lecco':'LC','lecce':'LE','livorno':'LI','lodi':'LO',
                'latina':'LT','lucca':'LU','monza e della brianza':'MB',
                'macerata':'MC','messina':'ME','milano':'MI','mantova':'MN',
                'modena':'MO','massa-carrara':'MS','matera':'MT','napoli':'NA',
                'novara':'NO','nuoro':'NU','oristano':'OR','palermo':'PA',
                'piacenza':'PC','padova':'PD','pescara':'PE','perugia':'PG',
                'pisa':'PI','pordenone':'PN','prato':'PO','parma':'PR',
                'pistoia':'PT','pesaro e urbino':'PU','pavia':'PV',
                'potenza':'PZ','ravenna':'RA','reggio calabria':'RC',
                'reggio emilia':'RE','ragusa':'RG','rieti':'RI','roma':'RM',
                'rimini':'RN','rovigo':'RO','salerno':'SA','siena':'SI',
                'sondrio':'SO','la spezia':'SP','siracusa':'SR','sassari':'SS',
                'sud sardegna':'SU','savona':'SV','taranto':'TA','teramo':'TE',
                'trento':'TN','torino':'TO','trapani':'TP','terni':'TR',
                'trieste':'TS','treviso':'TV','udine':'UD','varese':'VA',
                'verbano-cusio-ossola':'VB','vercelli':'VC','venezia':'VE',
                'vicenza':'VI','verona':'VR','viterbo':'VT','vibo valentia':'VV',
            }
            for nome, sig in NOME_SIGLA.items():
                if nome in pn_clean or pn_clean in nome:
                    sigla = sig
                    regione = PROV_REGIONE.get(sig, regione)
                    break

        if sigla:
            return jsonify({'trovato': True, 'provincia': sigla, 'regione': regione})
        elif regione:
            return jsonify({'trovato': True, 'provincia': None, 'regione': regione})
        else:
            return jsonify({'trovato': False})

    except Exception as ex:
        return jsonify({'trovato': False, 'errore': str(ex)})


@mercatini.route('/ai-crea-batch', methods=['POST'])
@csrf.exempt
@login_required
def ai_crea_batch():
    from ..models.mercatino import Mercatino as _Merc
    from datetime import datetime as _dt
    import json as _json

    data = request.get_json(silent=True) or {}
    eventi = data.get('eventi', [])
    if not eventi:
        return jsonify({'error': 'Nessun evento'}), 400

    creati = []
    errori = []

    for ev in eventi[:8]:
        try:
            m = _Merc()
            m.titolo = (ev.get('titolo') or 'Mercatino senza titolo').strip()[:200]
            m.descrizione  = ev.get('descrizione')
            m.citta        = ev.get('citta')
            m.regione      = ev.get('regione')
            m.provincia    = ev.get('provincia')
            m.indirizzo    = ev.get('indirizzo')
            m.orario       = ev.get('orario')
            m.sito_web     = ev.get('sito_web')
            m.telefono     = ev.get('telefono')
            m.email_contatto = ev.get('email_contatto')
            m.pubblicato   = False   # bozza: l'utente rivede e pubblica
            m.organizzatore_id = current_user.id
            if ev.get('numero_espositori'):
                try: m.numero_espositori = int(ev['numero_espositori'])
                except: pass
            for campo in ['data_inizio', 'data_fine']:
                v = ev.get(campo)
                if v:
                    try: setattr(m, campo, _dt.strptime(v, '%Y-%m-%d').date())
                    except: pass
            db.session.add(m)
            db.session.flush()
            creati.append({'id': m.id, 'titolo': m.titolo})
        except Exception as ex:
            errori.append({'titolo': ev.get('titolo', '?'), 'errore': str(ex)})

    if creati:
        db.session.commit()
    return jsonify({'ok': True, 'creati': creati, 'errori': errori})


# ------------------------------------------------------------------
# Mappa eventi
# ------------------------------------------------------------------
@mercatini.route('/mappa')
def mappa():
    from datetime import date
    oggi = date.today()
    totale = Mercatino.query.filter(
        Mercatino.pubblicato == True,
        Mercatino.data_fine >= oggi,
    ).count()
    return render_template('mercatini/mappa.html', totale=totale)


@mercatini.route('/api/mappa-data')
def mappa_data():
    from datetime import date
    from flask import jsonify as _json
    oggi = date.today()
    mercatini_q = (
        Mercatino.query
        .filter(Mercatino.pubblicato == True, Mercatino.data_fine >= oggi)
        .order_by(Mercatino.data_inizio)
        .all()
    )
    # Coord centri province italiane (fallback se lat/lon mancano)
    PROV = {
        'AG':(37.32,13.58),'AL':(44.91,8.62),'AN':(43.62,13.51),
        'AO':(45.74,7.32),'AP':(42.85,13.58),'AQ':(42.35,13.40),
        'AR':(43.46,11.88),'AT':(44.90,8.21),'AV':(40.91,15.03),
        'BA':(41.12,16.87),'BG':(45.69,9.67),'BI':(45.56,8.05),
        'BL':(46.14,12.22),'BN':(41.13,14.78),'BO':(44.49,11.34),
        'BR':(40.63,17.94),'BS':(45.54,10.22),'BT':(41.23,16.29),
        'BZ':(46.50,11.35),'CA':(39.22,9.11),'CB':(41.56,14.66),
        'CE':(41.08,14.33),'CH':(42.35,14.17),'CL':(37.49,13.93),
        'CN':(44.39,7.55),'CO':(45.81,9.08),'CR':(45.13,10.02),
        'CS':(39.30,16.25),'CT':(37.50,15.09),'CZ':(38.90,16.59),
        'EN':(37.56,14.28),'FC':(44.22,12.04),'FE':(44.83,11.62),
        'FG':(41.46,15.55),'FI':(43.77,11.25),'FM':(43.16,13.72),
        'FR':(41.64,13.35),'GE':(44.41,8.93),'GO':(45.94,13.62),
        'GR':(42.76,11.11),'IM':(43.88,8.03),'IS':(41.59,14.23),
        'KR':(39.08,17.12),'LC':(45.86,9.40),'LE':(40.35,18.17),
        'LI':(43.55,10.31),'LO':(45.31,9.50),'LT':(41.46,12.90),
        'LU':(43.84,10.50),'MB':(45.59,9.27),'MC':(43.30,13.45),
        'ME':(38.19,15.55),'MI':(45.46,9.19),'MN':(45.16,10.79),
        'MO':(44.65,10.93),'MS':(44.03,10.14),'MT':(40.66,16.60),
        'NA':(40.85,14.27),'NO':(45.45,8.62),'NU':(40.32,9.33),
        'OR':(39.90,8.59),'PA':(38.13,13.34),'PC':(44.99,9.66),
        'PD':(45.41,11.88),'PE':(42.46,14.21),'PG':(43.11,12.39),
        'PI':(43.72,10.40),'PN':(46.07,12.66),'PO':(43.88,11.10),
        'PR':(44.80,10.33),'PT':(43.93,10.91),'PU':(43.62,12.71),
        'PV':(45.18,9.16),'PZ':(40.64,15.80),'RA':(44.42,12.20),
        'RC':(38.11,15.66),'RE':(44.70,10.64),'RG':(36.93,14.74),
        'RI':(42.41,12.86),'RM':(41.89,12.51),'RN':(44.06,12.57),
        'RO':(45.07,11.79),'SA':(40.68,14.76),'SI':(43.32,11.33),
        'SO':(46.17,9.87),'SP':(44.10,9.82),'SR':(37.07,15.29),
        'SS':(40.73,8.56),'SU':(39.33,9.00),'SV':(44.30,8.48),
        'TA':(40.47,17.24),'TE':(42.66,13.70),'TN':(46.07,11.12),
        'TO':(45.07,7.68),'TP':(37.87,12.53),'TR':(42.56,12.65),
        'TS':(45.65,13.77),'TV':(45.67,12.24),'UD':(46.06,13.24),
        'VA':(45.82,8.83),'VB':(45.93,8.55),'VC':(45.32,8.42),
        'VE':(45.44,12.33),'VI':(45.55,11.54),'VR':(45.44,10.99),
        'VS':(39.75,8.83),'VT':(42.42,12.10),'VV':(38.67,16.10),
    }
    result = []
    for m in mercatini_q:
        if m.lat and m.lon:
            lat, lon = float(m.lat), float(m.lon)
        elif m.provincia and m.provincia.upper() in PROV:
            lat, lon = PROV[m.provincia.upper()]
            # Piccolo jitter per non sovrapporre marker stessa prov
            import random; random.seed(m.id)
            lat += random.uniform(-0.05, 0.05)
            lon += random.uniform(-0.05, 0.05)
        else:
            continue
        result.append({
            'id': m.id,
            'titolo': m.titolo,
            'citta': m.citta,
            'prov': m.provincia or '',
            'd_ini': m.data_inizio.strftime('%d/%m/%Y'),
            'd_fin': m.data_fine.strftime('%d/%m/%Y') if m.data_fine != m.data_inizio else '',
            'lat': round(lat, 5),
            'lon': round(lon, 5),
            'url': url_for('mercatini.dettaglio', id=m.id),
        })
    return _json(result)


# ------------------------------------------------------------------
# Recensioni
# ------------------------------------------------------------------
@mercatini.route('/<int:id>/recensione', methods=['POST'])
@login_required
def aggiungi_recensione(id):
    from app.models.mercatino import Recensione
    from datetime import date
    m = Mercatino.query.get_or_404(id)
    oggi = date.today()

    # Solo su eventi passati o in corso
    if m.data_inizio > oggi:
        flash('Puoi recensire solo mercatini già iniziati.', 'warning')
        return redirect(url_for('mercatini.dettaglio', id=id))

    # Una recensione per utente per mercatino
    esiste = Recensione.query.filter_by(
        user_id=current_user.id, mercatino_id=id).first()
    if esiste:
        flash('Hai già lasciato una recensione per questo mercatino.', 'info')
        return redirect(url_for('mercatini.dettaglio', id=id))

    voto = request.form.get('voto', type=int)
    testo = (request.form.get('testo') or '').strip()

    if not voto or voto < 1 or voto > 5:
        flash('Seleziona un voto da 1 a 5.', 'danger')
        return redirect(url_for('mercatini.dettaglio', id=id))
    if len(testo) < 20:
        flash('Scrivi almeno 20 caratteri nella recensione.', 'danger')
        return redirect(url_for('mercatini.dettaglio', id=id))
    if not request.form.get('dichiarazione'):
        flash('Devi dichiarare di aver partecipato al mercatino.', 'warning')
        return redirect(url_for('mercatini.dettaglio', id=id))

    r = Recensione(user_id=current_user.id, mercatino_id=id,
                   voto=voto, testo=testo, approvata=False)
    db.session.add(r)
    db.session.commit()
    flash('Grazie! La tua recensione è in attesa di approvazione.', 'success')
    return redirect(url_for('mercatini.dettaglio', id=id))
