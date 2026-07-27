"""
Blueprint chat — /chat
Integrazione Anthropic per rispondere a domande sui mercatini.
Sessione in-memory (max 5 scambi) lato server tramite Flask session.
"""
import json
import logging
from datetime import datetime, timezone

import anthropic
from flask import (
    render_template, request, jsonify, session,
    current_app, abort
)
from flask_login import login_required, current_user
from sqlalchemy import or_

from app import db, csrf
from app.chat import chat
from app.models.mercatino import Mercatino, Categoria

log = logging.getLogger(__name__)

MAX_EXCHANGES = 5   # coppie user/assistant mantenute in sessione
MAX_TOKENS    = 800


# ------------------------------------------------------------------ #
# Helper: recupera mercatini rilevanti dal DB per arricchire il prompt #
# ------------------------------------------------------------------ #
def _mercatini_context(query: str) -> str:
    """Cerca i mercatini più pertinenti alla query e li serializza."""
    ora = datetime.now(timezone.utc)
    terms = [t for t in query.lower().split() if len(t) > 2]

    qs = Mercatino.query.filter_by(pubblicato=True)
    if terms:
        filters = []
        for t in terms[:4]:
            pat = f'%{t}%'
            filters.append(Mercatino.titolo.ilike(pat))
            filters.append(Mercatino.descrizione.ilike(pat))
            filters.append(Mercatino.citta.ilike(pat))
            filters.append(Mercatino.regione.ilike(pat))
        qs = qs.filter(or_(*filters))

    mercatini = qs.order_by(Mercatino.data_inizio.asc()).limit(6).all()

    if not mercatini:
        # fallback: prossimi 6 mercatini
        mercatini = (
            Mercatino.query
            .filter_by(pubblicato=True)
            .filter(Mercatino.data_inizio >= ora)
            .order_by(Mercatino.data_inizio.asc())
            .limit(6)
            .all()
        )

    if not mercatini:
        return 'Nessun mercatino presente nel database.'

    righe = []
    for m in mercatini:
        cats = ', '.join(c.nome for c in m.categorie) or '—'
        stato = 'in corso' if m.is_in_corso else ('futuro' if m.is_futuro else 'passato')
        righe.append(
            f'- {m.titolo} | {m.citta}, {m.regione} | '
            f'{m.data_inizio.strftime("%d/%m/%Y")} – {m.data_fine.strftime("%d/%m/%Y")} | '
            f'Stato: {stato} | Categorie: {cats}'
        )
    return '\n'.join(righe)


def _system_prompt(ctx: str) -> str:
    ora = datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M')
    return (
        f'Sei l\'assistente di Mercatini App, la piattaforma italiana per trovare mercatini '
        f'artigianali, di antiquariato, biologici e di design. '
        f'Rispondi in italiano, in modo cordiale e conciso (max 3 paragrafi). '
        f'Usa solo le informazioni fornite qui sotto; se non sai rispondere dillo chiaramente. '
        f'Data e ora attuale: {ora}.\n\n'
        f'MERCATINI DISPONIBILI:\n{ctx}'
    )


# ------------------------------------------------------------------ #
# Route GET /chat/ — pagina chat                                       #
# ------------------------------------------------------------------ #
@chat.route('/')
@login_required
def index():
    return render_template('chat/index.html')


# ------------------------------------------------------------------ #
# Route POST /chat/ask — endpoint AJAX                                 #
# ------------------------------------------------------------------ #
@chat.route('/ask', methods=['POST'])
@login_required
def ask():
    api_key = current_app.config.get('ANTHROPIC_API_KEY')
    if not api_key or api_key.startswith('sk-ant-DA_INSERIRE'):
        return jsonify({'error': 'Chat AI non configurata (API key mancante).'}), 503

    data = request.get_json(silent=True) or {}
    user_msg = (data.get('message') or '').strip()
    if not user_msg:
        return jsonify({'error': 'Messaggio vuoto.'}), 400
    if len(user_msg) > 1000:
        return jsonify({'error': 'Messaggio troppo lungo (max 1000 caratteri).'}), 400

    # Storico sessione
    history = session.get('chat_history', [])

    # Contesto DB
    ctx = _mercatini_context(user_msg)
    system = _system_prompt(ctx)

    # Compila messages per Anthropic (max MAX_EXCHANGES scambi)
    messages = history[-(MAX_EXCHANGES * 2):]
    messages.append({'role': 'user', 'content': user_msg})

    try:
        model = current_app.config.get('ANTHROPIC_MODEL', 'claude-haiku-4-5-20251001')
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=model,
            max_tokens=MAX_TOKENS,
            system=system,
            messages=messages,
        )
        reply = response.content[0].text
    except anthropic.APIError as e:
        log.error(f'Anthropic API error: {e}')
        return jsonify({'error': 'Errore del servizio AI. Riprova tra poco.'}), 502

    # Aggiorna storico
    history.append({'role': 'user', 'content': user_msg})
    history.append({'role': 'assistant', 'content': reply})
    # Mantieni solo gli ultimi MAX_EXCHANGES scambi
    session['chat_history'] = history[-(MAX_EXCHANGES * 2):]
    session.modified = True

    return jsonify({'reply': reply})


# ------------------------------------------------------------------ #
# Route POST /chat/reset — svuota la sessione                          #
# ------------------------------------------------------------------ #
@chat.route('/reset', methods=['POST'])
@login_required
def reset():
    session.pop('chat_history', None)
    return jsonify({'ok': True})
