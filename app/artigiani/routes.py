"""
app/artigiani/routes.py
Area pubblica + dashboard artigiani hobbisti.
VETRINA SOLO: nessun acquisto, carrello o pagamento tra utenti.
"""
import json
import logging
import os
from datetime import datetime, timezone

from flask import (render_template, redirect, url_for, flash,
                   request, session, jsonify, current_app, abort,
                   send_from_directory)
from flask_login import current_user, login_required

from app import db
from app.artigiani import artigiani
from app.artigiani.utils import (
    get_current_hobbista, hobbista_required,
    allowed_file, salva_foto, elimina_foto_files, ricalcola_storage,
    MAX_FILE_MB
)
from app.models.hobbisti import (
    HobbistaAccount, HobbistaFoto, HobbistaPiano,
    HobbistaAbbonamento, HobbistaSegnalazione, StatoHobbista
)

log = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# AREA PUBBLICA (nessun login richiesto)
# ══════════════════════════════════════════════════════════════════════════════

@artigiani.route('/')
def elenco():
    """Elenco pubblico di tutti gli artigiani attivi."""
    q = request.args.get('q', '').strip()
    query = HobbistaAccount.query.filter_by(stato=StatoHobbista.attivo)
    if q:
        query = query.filter(
            db.or_(
                HobbistaAccount.nome_visualizzato.ilike(f'%{q}%'),
                HobbistaAccount.comune.ilike(f'%{q}%'),
                HobbistaAccount.bio_breve.ilike(f'%{q}%'),
            )
        )
    hobbisti = query.order_by(HobbistaAccount.data_registrazione.desc()).all()
    return render_template('artigiani/pubblico/elenco.html',
                           hobbisti=hobbisti, q=q)


@artigiani.route('/<slug>')
def profilo(slug):
    """Profilo pubblico del singolo artigiano (via slug, es. /artigiani/selinar)."""
    hobbista = HobbistaAccount.query.filter_by(slug=slug).first_or_404()
    if hobbista.stato != StatoHobbista.attivo:
        abort(404)
    foto = (HobbistaFoto.query
            .filter_by(account_id=hobbista.id)
            .order_by(HobbistaFoto.ordine)
            .all())
    is_following = False
    if current_user.is_authenticated:
        from app.models.follow import HobbistaFollow
        is_following = HobbistaFollow.query.filter_by(
            user_id=current_user.id, hobbista_id=hobbista.id, attivo=True
        ).first() is not None
    from app.models.follow import HobbistaEventoPartecipazione
    from datetime import date as _date
    oggi = _date.today()
    partecipazioni_attive = (HobbistaEventoPartecipazione.query
                             .filter_by(hobbista_id=hobbista.id)
                             .filter(HobbistaEventoPartecipazione.data_evento >= oggi)
                             .order_by(HobbistaEventoPartecipazione.data_evento)
                             .limit(6)
                             .all())
    return render_template('artigiani/pubblico/profilo.html',
                           hobbista=hobbista, foto=foto,
                           is_following=is_following,
                           partecipazioni_attive=partecipazioni_attive,
                           oggi=oggi)


@artigiani.route('/<int:hobbista_id>')
def profilo_redirect(hobbista_id):
    """Redirect 301 da URL numerico legacy al profilo con slug (backward compat + SEO)."""
    hobbista = HobbistaAccount.query.get_or_404(hobbista_id)
    if hobbista.slug:
        return redirect(url_for('artigiani.profilo', slug=hobbista.slug), 301)
    abort(404)


@artigiani.route('/termini')
def termini():
    """Pagina termini di servizio hobbisti."""
    return render_template('artigiani/termini.html')


# ── Serve foto tramite slug ────────────────────────────────────────────────────

@artigiani.route('/foto/<slug>/<path:filename>')
def serve_foto(slug, filename):
    """
    Serve una foto (o thumbnail) tramite slug artigiano.
    URL: /artigiani/foto/<slug>/<file>.jpg
         /artigiani/foto/<slug>/thumb/<file>.jpg
    """
    hobbista = HobbistaAccount.query.filter_by(slug=slug).first_or_404()
    upload_base = current_app.config['ARTIGIANI_UPLOAD_FOLDER']
    account_dir = os.path.join(upload_base, str(hobbista.id))
    return send_from_directory(account_dir, filename)


# Segnalazione pubblica foto (POST)
@artigiani.route('/<int:hobbista_id>/segnala', methods=['POST'])
def segnala(hobbista_id):
    hobbista = HobbistaAccount.query.get_or_404(hobbista_id)

    def _redirect_profilo():
        if hobbista.slug:
            return redirect(url_for('artigiani.profilo', slug=hobbista.slug))
        return redirect(url_for('artigiani.profilo_redirect', hobbista_id=hobbista_id))

    foto_id = request.form.get('foto_id', type=int)
    motivo  = request.form.get('motivo', '').strip()[:500]
    if not foto_id or not motivo:
        flash('Compila tutti i campi per inviare una segnalazione.', 'danger')
        return _redirect_profilo()

    foto = HobbistaFoto.query.get_or_404(foto_id)
    if foto.account_id != hobbista_id:
        abort(400)

    seg = HobbistaSegnalazione(foto_id=foto_id, motivo=motivo)
    db.session.add(seg)
    db.session.commit()
    flash('Segnalazione inviata. Grazie.', 'success')
    return _redirect_profilo()


# ══════════════════════════════════════════════════════════════════════════════
# DASHBOARD (login hobbista richiesto)
# ══════════════════════════════════════════════════════════════════════════════

@artigiani.route('/dashboard')
@hobbista_required
def dashboard():
    hobbista = get_current_hobbista()
    foto = (HobbistaFoto.query
            .filter_by(account_id=hobbista.id)
            .order_by(HobbistaFoto.ordine)
            .all())
    piani = HobbistaPiano.query.filter_by(attivo=True).order_by(
        HobbistaPiano.prezzo_mensile_eur).all()
    from app.models.follow import HobbistaEventoPartecipazione
    from datetime import date as _date
    partecipazioni = (HobbistaEventoPartecipazione.query
                      .filter_by(hobbista_id=hobbista.id)
                      .order_by(HobbistaEventoPartecipazione.data_evento.desc())
                      .all())
    oggi = _date.today()
    return render_template('artigiani/dashboard/home.html',
                           hobbista=hobbista, foto=foto, piani=piani,
                           partecipazioni=partecipazioni, oggi=oggi)


# ── Upload foto ───────────────────────────────────────────────────────────────

@artigiani.route('/dashboard/carica', methods=['GET', 'POST'])
@hobbista_required
def carica_foto():
    hobbista = get_current_hobbista()

    if request.method == 'POST':
        files      = request.files.getlist('foto')
        didascalie = request.form.getlist('didascalia')
        caricati   = 0
        errori     = []

        for idx, f in enumerate(files):
            if not f or not f.filename:
                continue
            if not allowed_file(f.filename):
                errori.append(f"{f.filename}: formato non supportato (usa JPG, PNG, WEBP).")
                continue

            f.seek(0, 2)
            size_bytes = f.tell()
            f.seek(0)
            if size_bytes > MAX_FILE_MB * 1024 * 1024:
                errori.append(f"{f.filename}: file troppo grande (max {MAX_FILE_MB} MB).")
                continue

            if (hobbista.storage_usato_mb + size_bytes / (1024 * 1024)
                    > hobbista.storage_max_mb + 5):
                errori.append("Spazio di archiviazione esaurito. "
                              "Elimina alcune foto o passa a un piano superiore.")
                break

            try:
                path_rel, filename, kb = salva_foto(f, hobbista.id)
            except Exception as e:
                log.error(f"Errore salvataggio foto: {e}")
                errori.append(f"{f.filename}: errore nel salvataggio.")
                continue

            did = didascalie[idx].strip()[:150] if idx < len(didascalie) else ''
            max_ord = (db.session.query(db.func.max(HobbistaFoto.ordine))
                       .filter_by(account_id=hobbista.id).scalar() or 0)

            foto = HobbistaFoto(
                account_id    = hobbista.id,
                filename      = filename,
                path_relativo = path_rel,
                didascalia    = did or None,
                dimensione_kb = kb,
                ordine        = max_ord + 1,
            )
            db.session.add(foto)
            db.session.commit()
            try:
                from app.models.follow import HobbistaFotoDigestQueue
                dq = HobbistaFotoDigestQueue(foto_id=foto.id, hobbista_id=hobbista.id)
                db.session.add(dq)
                db.session.commit()
            except Exception as _dq_err:
                log.warning(f'digest queue: {_dq_err}')
            ricalcola_storage(hobbista.id)
            caricati += 1

        if errori:
            for e in errori:
                flash(e, 'danger')
        if caricati:
            flash(f'{caricati} foto caricate con successo!', 'success')

        return redirect(url_for('artigiani.dashboard'))

    return render_template('artigiani/dashboard/carica_foto.html', hobbista=hobbista)


# ── Elimina foto ──────────────────────────────────────────────────────────────

@artigiani.route('/dashboard/foto/<int:foto_id>/elimina', methods=['POST'])
@hobbista_required
def elimina_foto(foto_id):
    hobbista = get_current_hobbista()
    foto = HobbistaFoto.query.get_or_404(foto_id)
    if foto.account_id != hobbista.id:
        abort(403)

    from app.models.follow import HobbistaFotoDigestQueue
    HobbistaFotoDigestQueue.query.filter_by(foto_id=foto.id).delete()
    HobbistaSegnalazione.query.filter_by(foto_id=foto.id).delete()

    elimina_foto_files(foto)
    db.session.delete(foto)
    db.session.commit()
    ricalcola_storage(hobbista.id)

    flash('Foto eliminata.', 'success')
    return redirect(url_for('artigiani.dashboard'))


# ── Riordina foto ─────────────────────────────────────────────────────────────

@artigiani.route('/dashboard/foto/riordina', methods=['POST'])
@hobbista_required
def riordina_foto():
    hobbista  = get_current_hobbista()
    ordinamento = request.get_json(silent=True) or {}

    for foto_id_str, ordine in ordinamento.items():
        try:
            foto_id = int(foto_id_str)
        except ValueError:
            continue
        foto = HobbistaFoto.query.get(foto_id)
        if foto and foto.account_id == hobbista.id:
            foto.ordine = int(ordine)
    db.session.commit()
    return jsonify({'ok': True})


# ── Modifica profilo ──────────────────────────────────────────────────────────

@artigiani.route('/dashboard/profilo', methods=['GET', 'POST'])
@hobbista_required
def modifica_profilo():
    hobbista = get_current_hobbista()

    if request.method == 'POST':
        hobbista.nome_visualizzato = request.form.get('nome_visualizzato', '').strip() or hobbista.nome_visualizzato
        hobbista.bio_breve         = (request.form.get('bio_breve', '').strip() or None)
        if hobbista.bio_breve:
            hobbista.bio_breve = hobbista.bio_breve[:200]
        hobbista.instagram_handle  = request.form.get('instagram_handle', '').strip() or None
        hobbista.whatsapp_number   = request.form.get('whatsapp_number', '').strip() or None
        hobbista.telegram_handle   = request.form.get('telegram_handle', '').strip() or None
        hobbista.comune            = request.form.get('comune', '').strip() or None
        db.session.commit()
        flash('Profilo aggiornato.', 'success')
        return redirect(url_for('artigiani.dashboard'))

    return render_template('artigiani/dashboard/profilo.html', hobbista=hobbista)


# ── Abbonamento ───────────────────────────────────────────────────────────────

@artigiani.route('/dashboard/abbonamento')
@hobbista_required
def abbonamento():
    hobbista = get_current_hobbista()
    piani = HobbistaPiano.query.filter_by(attivo=True).order_by(
        HobbistaPiano.prezzo_mensile_eur).all()
    return render_template('artigiani/dashboard/abbonamento.html',
                           hobbista=hobbista, piani=piani)


# ══════════════════════════════════════════════════════════════════════════════
# STRIPE CHECKOUT — PIANI HOBBISTI
# ══════════════════════════════════════════════════════════════════════════════

@artigiani.route('/dashboard/abbonamento/checkout/<int:piano_id>', methods=['POST'])
@hobbista_required
def abbonamento_checkout(piano_id):
    import stripe
    hobbista = get_current_hobbista()
    piano    = HobbistaPiano.query.get_or_404(piano_id)

    if not piano.stripe_price_id:
        flash("Piano non ancora disponibile per il pagamento online. Contattaci su WhatsApp.", "warning")
        return redirect(url_for("artigiani.abbonamento"))

    stripe.api_key = current_app.config["STRIPE_SECRET_KEY"]
    base_url = current_app.config.get("BASE_URL", "https://mercatini.blog")

    customer_id = hobbista.stripe_customer_id
    if not customer_id:
        customer = stripe.Customer.create(
            email=hobbista.email,
            name=hobbista.nome_visualizzato,
            metadata={"hobbista_id": str(hobbista.id)},
        )
        customer_id = customer.id
        hobbista.stripe_customer_id = customer_id
        db.session.commit()

    try:
        sess = stripe.checkout.Session.create(
            customer=customer_id,
            payment_method_types=["card"],
            line_items=[{"price": piano.stripe_price_id, "quantity": 1}],
            mode="subscription",
            success_url=base_url + url_for("artigiani.abbonamento_successo")
                        + "?session_id={CHECKOUT_SESSION_ID}",
            cancel_url=base_url + url_for("artigiani.abbonamento_cancellato"),
            metadata={"hobbista_id": str(hobbista.id), "piano_id": str(piano.id)},
            subscription_data={"metadata": {"hobbista_id": str(hobbista.id), "piano_id": str(piano.id)}},
        )
        return redirect(sess.url, code=303)
    except Exception as exc:
        log.error("Stripe checkout error: %s", exc)
        flash("Errore durante il pagamento. Riprova o contattaci.", "danger")
        return redirect(url_for("artigiani.abbonamento"))


@artigiani.route("/dashboard/abbonamento/successo")
@hobbista_required
def abbonamento_successo():
    hobbista = get_current_hobbista()
    return render_template("artigiani/dashboard/abbonamento_successo.html", hobbista=hobbista)


@artigiani.route("/dashboard/abbonamento/cancellato")
@hobbista_required
def abbonamento_cancellato():
    hobbista = get_current_hobbista()
    return render_template("artigiani/dashboard/abbonamento_cancellato.html", hobbista=hobbista)


@artigiani.route("/stripe-webhook-hobbisti", methods=["POST"])
def stripe_webhook_hobbisti():
    import stripe
    from datetime import timedelta

    stripe.api_key = current_app.config["STRIPE_SECRET_KEY"]
    payload    = request.get_data()
    sig_header = request.headers.get("Stripe-Signature", "")
    secret     = current_app.config.get("STRIPE_WEBHOOK_SECRET_HOBBISTI", "")

    if secret:
        try:
            event = stripe.Webhook.construct_event(payload, sig_header, secret)
        except (ValueError, stripe.error.SignatureVerificationError) as e:
            log.warning("Stripe webhook signature invalid: %s", e)
            abort(400)
    else:
        import json as _json
        event = _json.loads(payload)

    etype = event["type"]
    data  = event["data"]["object"]

    if etype == "checkout.session.completed":
        hobbista_id = int(data.get("metadata", {}).get("hobbista_id", 0))
        piano_id    = int(data.get("metadata", {}).get("piano_id", 0))
        sub_id      = data.get("subscription")
        session_id  = data.get("id")
        hobbista = db.session.get(HobbistaAccount, hobbista_id)
        piano    = db.session.get(HobbistaPiano, piano_id)
        if hobbista and piano:
            scadenza = datetime.now(timezone.utc) + timedelta(days=32)
            for old in hobbista.abbonamenti:
                if old.stato.value == 'attivo':
                    old.stato = 'scaduto'
            from app.models.hobbisti import StatoAbbonamento
            abb = HobbistaAbbonamento(
                account_id=hobbista.id, piano_id=piano.id,
                data_inizio=datetime.now(timezone.utc),
                data_scadenza=scadenza, stato=StatoAbbonamento.attivo,
                provider_pagamento="stripe",
                stripe_subscription_id=sub_id, stripe_session_id=session_id,
            )
            db.session.add(abb)
            hobbista.piano_id = piano.id
            db.session.commit()

    elif etype in ("customer.subscription.deleted", "customer.subscription.paused"):
        from app.models.hobbisti import StatoAbbonamento
        sub_id = data.get("id")
        abb = HobbistaAbbonamento.query.filter_by(
            stripe_subscription_id=sub_id, stato=StatoAbbonamento.attivo
        ).first()
        if abb:
            abb.stato = StatoAbbonamento.scaduto
            base = HobbistaPiano.query.order_by(HobbistaPiano.prezzo_mensile_eur).first()
            if base:
                abb.account.piano_id = base.id
            db.session.commit()

    elif etype == "invoice.paid":
        from datetime import timedelta
        from app.models.hobbisti import StatoAbbonamento
        sub_id = data.get("subscription")
        abb = HobbistaAbbonamento.query.filter_by(
            stripe_subscription_id=sub_id, stato=StatoAbbonamento.attivo
        ).first()
        if abb:
            abb.data_scadenza = datetime.now(timezone.utc) + timedelta(days=32)
            db.session.commit()

    return ("", 200)


# ── Modifica didascalia foto (AJAX) ───────────────────────────────────────────

@artigiani.route('/dashboard/foto/<int:foto_id>/didascalia', methods=['POST'])
@hobbista_required
def modifica_didascalia(foto_id):
    hobbista = get_current_hobbista()
    foto = HobbistaFoto.query.get_or_404(foto_id)
    if foto.account_id != hobbista.id:
        abort(403)
    did = request.form.get('didascalia', '').strip()[:150]
    foto.didascalia = did or None
    db.session.commit()
    return jsonify({'ok': True, 'didascalia': foto.didascalia or ''})


# ══════════════════════════════════════════════════════════════════════════════
# FOLLOW / SEGUI ARTIGIANI
# ══════════════════════════════════════════════════════════════════════════════

@artigiani.route('/<int:hobbista_id>/segui', methods=['POST'])
@login_required
def segui(hobbista_id):
    from app.models.follow import HobbistaFollow
    hobbista = HobbistaAccount.query.get_or_404(hobbista_id)
    follow = HobbistaFollow.query.filter_by(
        user_id=current_user.id, hobbista_id=hobbista_id
    ).first()
    if follow:
        follow.attivo = True
    else:
        follow = HobbistaFollow(user_id=current_user.id, hobbista_id=hobbista_id)
        db.session.add(follow)
    db.session.commit()
    return jsonify({'seguendo': True, 'msg': f'Stai seguendo {hobbista.nome_visualizzato}'})


@artigiani.route('/<int:hobbista_id>/smetti-di-seguire', methods=['POST'])
@login_required
def smetti_di_seguire(hobbista_id):
    from app.models.follow import HobbistaFollow
    follow = HobbistaFollow.query.filter_by(
        user_id=current_user.id, hobbista_id=hobbista_id, attivo=True
    ).first()
    if follow:
        follow.attivo = False
        db.session.commit()
    return jsonify({'seguendo': False})


# ── Dichiara partecipazione evento ───────────────────────────────────────────

@artigiani.route('/dashboard/eventi/dichiara-partecipazione', methods=['GET', 'POST'])
@hobbista_required
def dichiara_partecipazione():
    from app.models.follow import HobbistaEventoPartecipazione
    from app.models.mercatino import Mercatino
    from datetime import date
    hobbista = get_current_hobbista()

    if request.method == 'POST':
        merc_id     = request.form.get('mercatino_id', type=int) or None
        nome_ev     = request.form.get('nome_evento', '').strip()[:200]
        data_ev_str = request.form.get('data_evento', '')
        luogo_ev    = request.form.get('luogo_evento', '').strip()[:200]
        msg         = request.form.get('messaggio_breve', '').strip()[:200]

        if not merc_id and not nome_ev:
            flash("Seleziona un mercatino dal catalogo oppure inserisci il nome dell'evento.", 'danger')
            return redirect(request.url)

        data_ev = None
        if data_ev_str:
            try:
                data_ev = datetime.strptime(data_ev_str, '%Y-%m-%d').date()
            except ValueError:
                pass

        part = HobbistaEventoPartecipazione(
            hobbista_id=hobbista.id, mercatino_id=merc_id,
            nome_evento=nome_ev or None, data_evento=data_ev,
            luogo_evento=luogo_ev or None, messaggio_breve=msg or None,
        )
        db.session.add(part)
        db.session.commit()

        try:
            from app.tasks import invia_notifica_evento
            invia_notifica_evento(current_app._get_current_object(), part.id)
        except Exception as exc:
            log.warning(f'Notifica evento non inviata: {exc}')

        flash('Partecipazione dichiarata! I tuoi follower verranno avvisati.', 'success')
        return redirect(url_for('artigiani.dashboard'))

    from datetime import date, timedelta
    prossimi = (
        Mercatino.query
        .filter(Mercatino.pubblicato == True, Mercatino.data_inizio >= date.today())
        .order_by(Mercatino.data_inizio.asc()).limit(50).all()
    )
    return render_template('artigiani/dashboard/dichiara_partecipazione.html',
                           hobbista=hobbista, prossimi=prossimi)
