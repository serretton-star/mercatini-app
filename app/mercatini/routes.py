from datetime import date
from flask import render_template, redirect, url_for, flash, request, abort, jsonify
from flask_login import login_required, current_user
from sqlalchemy import or_
from app import db, csrf
from app.auth.routes import notifica_nuovi_eventi
from app.models import Mercatino, Categoria
from app.mercatini import mercatini
from app.mercatini.forms import MercatinoForm


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
# Lista mercatini
# ------------------------------------------------------------------
@mercatini.route('/')
def index():
    page = request.args.get('page', 1, type=int)
    q = request.args.get('q', '', type=str).strip()
    regione = request.args.get('regione', '', type=str).strip()
    citta = request.args.get('citta', '', type=str).strip()
    cat_id = request.args.get('categoria', 0, type=int)
    provincia = request.args.get('provincia', '', type=str).strip()
    data_dal = request.args.get('data_dal', '', type=str).strip()
    data_al  = request.args.get('data_al',  '', type=str).strip()

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
    if provincia:
        query = query.filter(Mercatino.provincia.ilike(f'%{provincia}%'))
    if data_dal:
        try:
            from datetime import date as _d
            query = query.filter(Mercatino.data_fine >= _d.fromisoformat(data_dal))
        except ValueError:
            pass
    if data_al:
        try:
            from datetime import date as _d
            query = query.filter(Mercatino.data_inizio <= _d.fromisoformat(data_al))
        except ValueError:
            pass

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
        filtro_provincia=provincia,
        filtro_data_dal=data_dal,
        filtro_data_al=data_al,
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
            ingresso_gratuito=form.ingresso_gratuito.data,
            prezzo_ingresso=form.prezzo_ingresso.data if not form.ingresso_gratuito.data else None,
            numero_espositori=form.numero_espositori.data or None,
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
        m.ingresso_gratuito = form.ingresso_gratuito.data
        m.prezzo_ingresso = form.prezzo_ingresso.data if not form.ingresso_gratuito.data else None
        m.numero_espositori = form.numero_espositori.data or None
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
    CAMPO = '{"titolo":null,"descrizione":null,"citta":null,"regione":null,"provincia":null,"indirizzo":null,"data_inizio":null,"data_fine":null,"orario":null,"ingresso_gratuito":true,"prezzo_ingresso":null,"numero_espositori":null,"sito_web":null,"telefono":null,"email_contatto":null}'

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
        '"orario":null,"ingresso_gratuito":true,"prezzo_ingresso":null,'
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
            m.ingresso_gratuito = bool(ev.get('ingresso_gratuito', True))
            m.pubblicato   = False   # bozza: l'utente rivede e pubblica
            m.organizzatore_id = current_user.id
            if ev.get('numero_espositori'):
                try: m.numero_espositori = int(ev['numero_espositori'])
                except: pass
            if ev.get('prezzo_ingresso'):
                try: m.prezzo_ingresso = float(ev['prezzo_ingresso'])
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
