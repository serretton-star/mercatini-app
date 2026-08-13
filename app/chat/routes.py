"""
Blueprint chat — /chat
Integrazione Anthropic per rispondere a domande sui mercatini.
"""
import logging
import re
import urllib.parse
from collections import Counter
from datetime import datetime, timezone, date as _date

import anthropic
from flask import render_template, request, jsonify, session, current_app
from flask_login import login_required, current_user
from sqlalchemy import or_

from app import db
from app.chat import chat
from app.models.mercatino import Mercatino, Categoria

log = logging.getLogger(__name__)
MAX_EXCHANGES = 5
MAX_TOKENS    = 1200

STOPWORDS = {
    'mercatini', 'mercatino', 'nel', 'nella', 'nelle', 'nei', 'del', 'della',
    'delle', 'dei', 'di', 'a', 'in', 'al', 'alle', 'per', 'con', 'che',
    'sono', 'come', 'dove', 'quando', 'quali', 'cosa', 'vorrei', 'trovare',
    'cerco', 'vicino', 'intorno', 'zona', 'area', 'lago',
}

def _extract_terms(query: str):
    """Estrae termini significativi dalla query (no stopwords, min 3 char)."""
    words = re.findall(r'[a-zA-ZàèéìòùÀÈÉÌÒÙ]+', query.lower())
    return [w for w in words if len(w) >= 3 and w not in STOPWORDS]


def _mercatini_context(query: str):
    """Restituisce (context_str, selezione_ai, cards_matched).
    - selezione_ai  : mercatini per il contesto AI (con fallback)
    - cards_matched : SOLO quelli effettivamente matchati dalla query (no fallback)
    """
    oggi = _date.today()
    tutti = Mercatino.query.filter_by(pubblicato=True).all()
    totale = len(tutti)
    if totale == 0:
        return 'Nessun mercatino pubblicato.', [], []

    per_regione = Counter(m.regione or 'N/D' for m in tutti)
    futuri   = sum(1 for m in tutti if m.data_inizio and m.data_inizio > oggi)
    in_corso = sum(1 for m in tutti if m.data_inizio and m.data_fine
                   and m.data_inizio <= oggi <= m.data_fine)
    passati  = totale - futuri - in_corso
    regioni_str = ', '.join(
        f'{r}: {n}' for r, n in sorted(per_regione.items(), key=lambda x: -x[1])
    )
    summary = (
        'RIEPILOGO DATABASE:\n'
        f'  Totale: {totale} | In corso: {in_corso} | Futuri: {futuri} | Passati: {passati}\n'
        f'  Per regione -> {regioni_str}\n'
    )

    query_lower = query.lower()
    PAROLE_GENERALI = {'tutti', 'quanti', 'lista', 'elenco', 'mostra', 'elenca',
                       'disponibili', 'totale', 'esistono'}
    is_generale = any(p in query_lower for p in PAROLE_GENERALI) or len(query_lower.split()) <= 2

    terms = _extract_terms(query)

    # --- Ricerca specifica con i termini estratti ---
    cards_matched = []
    if terms and not is_generale:
        filters = []
        for t in terms[:6]:
            pat = f'%{t}%'
            filters.append(Mercatino.titolo.ilike(pat))
            filters.append(Mercatino.descrizione.ilike(pat))
            filters.append(Mercatino.citta.ilike(pat))
            filters.append(Mercatino.regione.ilike(pat))
            filters.append(Mercatino.provincia.ilike(pat))
            filters.append(Mercatino.indirizzo.ilike(pat))
        cards_matched = (Mercatino.query
                         .filter_by(pubblicato=True)
                         .filter(or_(*filters))
                         .order_by(Mercatino.data_inizio.asc())
                         .limit(20).all())

    # --- Contesto AI: usa matched se c'è, altrimenti fallback ---
    if is_generale:
        selezione_ai = sorted(tutti, key=lambda m: (m.data_inizio or oggi))[:50]
    elif cards_matched:
        selezione_ai = cards_matched
    else:
        selezione_ai = (Mercatino.query
                        .filter_by(pubblicato=True)
                        .order_by(Mercatino.data_inizio.asc())
                        .limit(30).all())

    righe = []
    for m in selezione_ai:
        try:
            cats = ', '.join(cat.nome for cat in m.categorie) or '-'
        except Exception:
            cats = '-'
        d_ini = m.data_inizio.strftime('%d/%m/%Y') if m.data_inizio else '?'
        d_fin = m.data_fine.strftime('%d/%m/%Y') if m.data_fine else '?'
        if m.data_inizio and m.data_fine:
            stato = ('IN CORSO' if m.data_inizio <= oggi <= m.data_fine
                     else ('futuro' if m.data_inizio > oggi else 'passato'))
        else:
            stato = '?'
        contatti = []
        if m.telefono:        contatti.append(f'tel:{m.telefono}')
        if m.email_contatto:  contatti.append(f'email:{m.email_contatto}')
        # Voto medio recensioni
        rec_approvate = [r for r in m.recensioni if r.approvata]
        if rec_approvate:
            voto_medio = round(sum(r.voto for r in rec_approvate) / len(rec_approvate), 1)
            voto_str = f' | valutazione: {voto_medio}/5 ({len(rec_approvate)} rec.)'
        else:
            voto_str = ''
        righe.append(
            f'- {m.titolo} | {m.citta or "?"}, {m.regione or "?"} ({m.provincia or "?"}) '
            f'| {d_ini}-{d_fin} | {stato} | {cats}'
            + (f' | {" | ".join(contatti)}' if contatti else '')
            + voto_str
        )

    dettagli = (
        f'DETTAGLIO ({len(selezione_ai)} su {totale}):\n' + '\n'.join(righe)
    )
    return summary + '\n' + dettagli, selezione_ai, cards_matched


def _serialize_cards(mercatini, oggi):
    """Serializza max 10 mercatini non passati per le card frontend."""
    out = []
    for m in mercatini:
        if m.data_fine and m.data_fine < oggi:
            continue
        maps_q = urllib.parse.quote(
            ' '.join(filter(None, [m.indirizzo, m.citta, m.provincia, m.regione, 'Italia']))
        )
        tel_digits = re.sub(r'\D', '', m.telefono or '')
        if tel_digits.startswith('0'):
            tel_wa = '39' + tel_digits
        elif tel_digits.startswith('39'):
            tel_wa = tel_digits
        else:
            tel_wa = tel_digits
        d_ini = m.data_inizio.strftime('%d/%m/%Y') if m.data_inizio else ''
        d_fin = m.data_fine.strftime('%d/%m/%Y')   if m.data_fine   else ''
        rec = [r for r in m.recensioni if r.approvata]
        voto = round(sum(r.voto for r in rec) / len(rec), 1) if rec else None
        out.append({
            'id':        m.id,
            'titolo':    m.titolo,
            'citta':     m.citta or '',
            'provincia': m.provincia or '',
            'regione':   m.regione or '',
            'indirizzo': m.indirizzo or '',
            'd_ini':     d_ini,
            'd_fin':     d_fin,
            'telefono':  m.telefono or '',
            'tel_wa':    tel_wa,
            'email':     m.email_contatto or '',
            'maps_url':  f'https://www.google.com/maps/search/?api=1&query={maps_q}',
            'voto':      voto,
            'n_rec':     len(rec),
        })
        if len(out) >= 10:
            break
    return out


def _system_prompt(ctx: str) -> str:
    ora = datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M')
    return (
        "Sei l'assistente di Mercatini App, la piattaforma italiana per trovare mercatini "
        "artigianali, di antiquariato, biologici e di design. "
        "Rispondi in italiano, in modo cordiale e conciso (max 4 paragrafi). "
        "Usa SOLO le informazioni qui sotto. "
        f"Data e ora: {ora}.\n\n{ctx}"
    )


@chat.route('/')
@login_required
def index():
    return render_template('chat/index.html')


@chat.route('/ask', methods=['POST'])
@login_required
def ask():
    api_key = current_app.config.get('ANTHROPIC_API_KEY')
    if not api_key or api_key.startswith('sk-ant-DA_INSERIRE'):
        return jsonify({'error': 'Chat AI non configurata.'}), 503

    data = request.get_json(silent=True) or {}
    user_msg = (data.get('message') or '').strip()
    if not user_msg:
        return jsonify({'error': 'Messaggio vuoto.'}), 400
    if len(user_msg) > 1000:
        return jsonify({'error': 'Messaggio troppo lungo.'}), 400

    history = session.get('chat_history', [])
    ctx, _selezione_ai, cards_matched = _mercatini_context(user_msg)
    system = _system_prompt(ctx)

    messages = history[-(MAX_EXCHANGES * 2):]
    messages.append({'role': 'user', 'content': user_msg})

    try:
        model  = current_app.config.get('ANTHROPIC_MODEL', 'claude-haiku-4-5-20251001')
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=model, max_tokens=MAX_TOKENS, system=system, messages=messages,
        )
        reply = response.content[0].text
    except anthropic.APIError as e:
        log.error(f'Anthropic API error: {e}')
        return jsonify({'error': 'Errore AI. Riprova.'}), 502

    history.append({'role': 'user', 'content': user_msg})
    history.append({'role': 'assistant', 'content': reply})
    session['chat_history'] = history[-(MAX_EXCHANGES * 2):]
    session.modified = True
    current_user.increment_chat()

    # Card: SOLO mercatini che matchano la query, nessun fallback
    oggi = _date.today()
    # Se keyword match -> card precise; altrimenti mostra i mercatini che l'AI ha descritto
    fonte_cards = cards_matched if cards_matched else _selezione_ai
    mercatini_cards = _serialize_cards(fonte_cards, oggi)

    # Meteo per eventi in card entro 7 giorni
    from datetime import date as _dt, timedelta
    oggi2 = _dt.today()
    limite7 = oggi2 + timedelta(days=7)
    ow_key = current_app.config.get('OPENWEATHER_API_KEY', '')
    if ow_key and mercatini_cards:
        import requests as _req
        weather_cache = {}
        for card in mercatini_cards:
            try:
                d_ini_str = card.get('d_ini', '')
                if not d_ini_str:
                    continue
                from datetime import datetime as _dtt
                d_ini_date = _dtt.strptime(d_ini_str, '%d/%m/%Y').date()
                if d_ini_date > limite7:
                    continue
                city = card['citta']
                if city not in weather_cache:
                    resp = _req.get(
                        'https://api.openweathermap.org/data/2.5/forecast',
                        params={'q': f'{city},IT', 'appid': ow_key,
                                'units': 'metric', 'lang': 'it', 'cnt': 8},
                        timeout=3)
                    weather_cache[city] = resp.json() if resp.status_code == 200 else {}
                wd = weather_cache.get(city, {})
                if wd.get('list'):
                    first = wd['list'][0]
                    card['meteo'] = {
                        'temp': round(first['main']['temp']),
                        'desc': first['weather'][0]['description'],
                    }
            except Exception:
                pass

    return jsonify({'reply': reply, 'mercatini': mercatini_cards})


@chat.route('/reset', methods=['POST'])
@login_required
def reset():
    session.pop('chat_history', None)
    return jsonify({'ok': True})
