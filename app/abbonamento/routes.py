import stripe
import logging
from datetime import datetime, timezone, timedelta
from flask import (current_app, redirect, render_template,
                   request, url_for, flash, abort)
from flask_login import login_required, current_user

from app import db, csrf
from app.abbonamento import abbonamento
from app.models.user import User

log = logging.getLogger(__name__)

PIANI = [
    {
        'chiave': '1m',
        'nome': 'Mensile',
        'prezzo': '€4',
        'sottotitolo': 'al mese',
        'cpm': None,
        'descrizione': 'Nessun impegno',
        'mesi': 1,
        'badge': None,
    },
    {
        'chiave': '3m',
        'nome': 'Trimestrale',
        'prezzo': '€10',
        'sottotitolo': 'ogni 3 mesi',
        'cpm': '≈€3,33/mese',
        'descrizione': None,
        'mesi': 3,
        'badge': None,
    },
    {
        'chiave': '6m',
        'nome': 'Semestrale',
        'prezzo': '€18',
        'sottotitolo': 'ogni 6 mesi',
        'cpm': '≈€3/mese',
        'descrizione': None,
        'mesi': 6,
        'badge': 'Il più scelto',
    },
    {
        'chiave': '12m',
        'nome': 'Annuale',
        'prezzo': '€30',
        'sottotitolo': "all’anno",
        'cpm': '≈€2,50/mese',
        'descrizione': None,
        'mesi': 12,
        'badge': None,
    },
]

PRICE_MAP = {
    '1m':  lambda: current_app.config['STRIPE_PRICE_1M'],
    '3m':  lambda: current_app.config['STRIPE_PRICE_3M'],
    '6m':  lambda: current_app.config['STRIPE_PRICE_6M'],
    '12m': lambda: current_app.config['STRIPE_PRICE_12M'],
}


@abbonamento.route('/')
@login_required
def piani():
    return render_template('abbonamento/piani.html', piani=PIANI)


@abbonamento.route('/checkout', methods=['POST'])
@login_required
def checkout():
    piano = request.form.get('piano')
    if piano not in PRICE_MAP:
        flash('Piano non valido.', 'danger')
        return redirect(url_for('abbonamento.piani'))

    stripe.api_key = current_app.config['STRIPE_SECRET_KEY']
    price_id = PRICE_MAP[piano]()
    mesi = next(p['mesi'] for p in PIANI if p['chiave'] == piano)

    try:
        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            mode='payment',
            line_items=[{'price': price_id, 'quantity': 1}],
            customer_email=current_user.email,
            metadata={'user_id': str(current_user.id), 'durata_mesi': str(mesi), 'piano': piano},
            invoice_creation={'enabled': True},
            success_url=url_for('abbonamento.successo', _external=True)
                        + '?session_id={CHECKOUT_SESSION_ID}',
            cancel_url=url_for('abbonamento.annullato', _external=True),
            locale='it',
        )
        return redirect(session.url, code=303)
    except stripe.error.StripeError as e:
        log.error('Stripe checkout error: %s', e)
        flash('Errore nel pagamento. Riprova più tardi.', 'danger')
        return redirect(url_for('abbonamento.piani'))


@abbonamento.route('/successo')
@login_required
def successo():
    session_id = request.args.get('session_id', '')
    return render_template('abbonamento/successo.html', session_id=session_id)


@abbonamento.route('/annullato')
@login_required
def annullato():
    return render_template('abbonamento/annullato.html')


@abbonamento.route('/webhook', methods=['POST'])
@csrf.exempt
def webhook():
    payload = request.get_data()
    sig_header = request.headers.get('Stripe-Signature', '')
    secret = current_app.config['STRIPE_WEBHOOK_SECRET']
    stripe.api_key = current_app.config['STRIPE_SECRET_KEY']

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, secret)
    except (ValueError, stripe.error.SignatureVerificationError) as e:
        log.warning('Webhook invalid: %s', e)
        abort(400)

    if event['type'] == 'checkout.session.completed':
        session = event['data']['object']
        _handle_payment(session)

    return '', 200


def _handle_payment(session):
    user_id    = int(session['metadata'].get('user_id', 0))
    durata     = int(session['metadata'].get('durata_mesi', 1))
    customer   = session.get('customer')

    user = db.session.get(User, user_id)
    if not user:
        log.error('Webhook: utente %s non trovato', user_id)
        return

    now = datetime.now(timezone.utc)
    # Se l'abbonamento è ancora attivo, estende dalla scadenza attuale
    base = user.subscription_end if (user.subscription_end and user.subscription_end > now) else now
    user.subscription_end = base + timedelta(days=30 * durata)

    if customer and not user.stripe_customer_id:
        user.stripe_customer_id = customer

    user.subscription_plan = session['metadata'].get('piano', '1m')
    user.ai_chat_count = 0
    user.ai_chat_reset = None
    db.session.commit()
    log.info('User %s abbonato fino al %s (piano %s)', user_id, user.subscription_end, user.subscription_plan)
