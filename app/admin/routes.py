from functools import wraps
from flask import render_template, redirect, url_for, flash, abort, request
from flask_login import login_required, current_user
from app import db
from app.models import User, Mercatino, Categoria, Recensione
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
        'recensioni_da_approvare': Recensione.query.filter_by(approvata=False).count(),
        'bozze_crawler': Mercatino.query.filter(
            Mercatino.pubblicato == False,
            Mercatino.fonte_crawler.isnot(None)
        ).count(),
    }
    recensioni_pending = (
        Recensione.query
        .filter_by(approvata=False)
        .order_by(Recensione.created_at.desc())
        .all()
    )
    mercatini = (
        Mercatino.query
        .order_by(Mercatino.created_at.desc())
        .limit(50)
        .all()
    )
    utenti = User.query.order_by(User.created_at.desc()).all()
    bozze_crawler = (
        Mercatino.query
        .filter(Mercatino.pubblicato == False, Mercatino.fonte_crawler.isnot(None))
        .order_by(Mercatino.created_at.desc())
        .all()
    )
    categorie = Categoria.query.order_by(Categoria.nome).all()
    # Doppioni: stesso titolo + stessa città + stessa data_inizio
    from collections import Counter
    _keys = [
        (m.titolo.strip().lower(),
         (m.citta or '').strip().lower(),
         m.data_inizio)
        for m in mercatini
    ]
    _cnt = Counter(_keys)
    id_doppioni = {m.id for m in mercatini
                   if _cnt[(m.titolo.strip().lower(),
                             (m.citta or '').strip().lower(),
                             m.data_inizio)] > 1}
    return render_template(
        'admin/dashboard.html',
        stats=stats,
        mercatini=mercatini,
        utenti=utenti,
        categorie=categorie,
        recensioni_pending=recensioni_pending,
        bozze_crawler=bozze_crawler,
        id_doppioni=id_doppioni,
    )



@admin.route('/mercatino/<int:id>/elimina', methods=['POST'])
@admin_required
def elimina_mercatino(id):
    from app.models.mercatino import Mercatino
    m = Mercatino.query.get_or_404(id)
    titolo = m.titolo
    db.session.delete(m)
    db.session.commit()
    flash(f'Evento "{titolo}" eliminato definitivamente.', 'success')
    return redirect(url_for('admin.dashboard'))

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


# ------------------------------------------------------------------
# Gestione Recensioni
# ------------------------------------------------------------------
@admin.route('/recensione/<int:id>/approva', methods=['POST'])
@login_required
@admin_required
def approva_recensione(id):
    r = Recensione.query.get_or_404(id)
    r.approvata = True
    db.session.commit()
    flash(f'Recensione approvata.', 'success')
    return redirect(url_for('admin.dashboard'))


@admin.route('/recensione/<int:id>/rifiuta', methods=['POST'])
@login_required
@admin_required
def rifiuta_recensione(id):
    r = Recensione.query.get_or_404(id)
    db.session.delete(r)
    db.session.commit()
    flash('Recensione rifiutata ed eliminata.', 'success')
    return redirect(url_for('admin.dashboard'))


# ------------------------------------------------------------------
# Gestione Bozze Crawler
# ------------------------------------------------------------------
@admin.route('/bozza/<int:id>/pubblica', methods=['POST'])
@login_required
@admin_required
def pubblica_bozza(id):
    m = Mercatino.query.get_or_404(id)
    m.pubblicato = True
    db.session.commit()
    flash(f'"{m.titolo}" pubblicato!', 'success')
    return redirect(url_for('admin.dashboard') + '#bozze-crawler')


@admin.route('/bozza/<int:id>/elimina', methods=['POST'])
@login_required
@admin_required
def elimina_bozza(id):
    m = Mercatino.query.get_or_404(id)
    titolo = m.titolo
    db.session.delete(m)
    db.session.commit()
    flash(f'Bozza "{titolo}" eliminata.', 'success')
    return redirect(url_for('admin.dashboard') + '#bozze-crawler')


@admin.route('/landing-stats')
@login_required
@admin_required
def landing_stats():
    from app.models.landing import LandingVisit
    from datetime import datetime, timezone, timedelta
    from sqlalchemy import func
    now = datetime.now(timezone.utc)
    oggi = now.date()
    d7  = datetime(*(oggi - timedelta(days=7)).timetuple()[:3], tzinfo=timezone.utc)
    d30 = datetime(*(oggi - timedelta(days=30)).timetuple()[:3], tzinfo=timezone.utc)
    totale      = LandingVisit.query.count()
    oggi_n      = LandingVisit.query.filter(
                      func.date(LandingVisit.timestamp) == oggi).count()
    settimana_n = LandingVisit.query.filter(LandingVisit.timestamp >= d7).count()
    mese_n      = LandingVisit.query.filter(LandingVisit.timestamp >= d30).count()
    daily = db.session.query(
        func.date(LandingVisit.timestamp).label('giorno'),
        func.count().label('n')
    ).filter(LandingVisit.timestamp >= d30).group_by('giorno').order_by('giorno').all()
    referrer_q = db.session.query(
        LandingVisit.referrer,
        func.count().label('n')
    ).filter(
        LandingVisit.referrer != '',
        LandingVisit.referrer.isnot(None)
    ).group_by(LandingVisit.referrer).order_by(func.count().desc()).limit(10).all()
    recenti = LandingVisit.query.order_by(LandingVisit.timestamp.desc()).limit(20).all()
    return render_template('admin/landing_stats.html',
        totale=totale, oggi_n=oggi_n, settimana_n=settimana_n, mese_n=mese_n,
        daily=daily, referrer_q=referrer_q, recenti=recenti)


@admin.route('/abbonamenti')
@login_required
@admin_required
def abbonamenti():
    from datetime import datetime, timezone, timedelta
    from app.models import User
    now = datetime.now(timezone.utc)
    soglia_recente = now - timedelta(days=30)

    attivi = (
        User.query
        .filter(User.piano_abbonamento != None,
                User.piano_abbonamento != 'free',
                User.abbonamento_scadenza > now)
        .order_by(User.abbonamento_scadenza.asc())
        .all()
    )
    scaduti_recenti = (
        User.query
        .filter(User.abbonamento_scadenza != None,
                User.abbonamento_scadenza <= now,
                User.abbonamento_scadenza >= soglia_recente)
        .order_by(User.abbonamento_scadenza.desc())
        .all()
    )
    return render_template('admin/abbonamenti.html',
        attivi=attivi,
        scaduti_recenti=scaduti_recenti,
        now=now,
    )


@admin.route('/esegui-crawler', methods=['POST'])
@login_required
@admin_required
def esegui_crawler():
    import subprocess, os, signal
    PID_FILE = '/var/www/mercatini/logs/crawler.pid'
    # Controlla se è già in esecuzione
    if os.path.exists(PID_FILE):
        try:
            with open(PID_FILE) as f:
                pid = int(f.read().strip())
            os.kill(pid, 0)  # signal 0 = check esistenza processo
            flash('⚠️ Crawler già in esecuzione (PID {}).'.format(pid), 'warning')
            return redirect(url_for('admin.dashboard'))
        except (ProcessLookupError, ValueError):
            os.remove(PID_FILE)  # processo morto, rimuovi PID vecchio

    # Avvia crawler in background
    try:
        proc = subprocess.Popen(
            ['/var/www/mercatini/scripts/run_crawler.sh'],
            stdout=open('/var/www/mercatini/logs/crawler.log', 'a'),
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        with open(PID_FILE, 'w') as f:
            f.write(str(proc.pid))
        flash(f'🤖 Crawler avviato in background (PID {proc.pid}). Controlla le bozze tra qualche minuto.', 'success')
    except Exception as e:
        flash(f'Errore avvio crawler: {e}', 'danger')
    return redirect(url_for('admin.dashboard'))

# ── MODERAZIONE ARTIGIANI HOBBISTI ────────────────────────────────────────────

@admin.route('/artigiani')
@login_required
@admin_required
def artigiani_lista():
    from app.models.hobbisti import HobbistaAccount, HobbistaSegnalazione, StatoHobbista
    hobbisti = HobbistaAccount.query.order_by(HobbistaAccount.data_registrazione.desc()).all()
    segnalazioni_aperte = HobbistaSegnalazione.query.filter_by(stato_gestione='da_rivedere').count()
    return render_template('admin/artigiani.html',
                           hobbisti=hobbisti,
                           segnalazioni_aperte=segnalazioni_aperte,
                           StatoHobbista=StatoHobbista)


@admin.route('/artigiani/<int:hobbista_id>/stato', methods=['POST'])
@login_required
@admin_required
def artigiani_stato(hobbista_id):
    from app.models.hobbisti import HobbistaAccount, StatoHobbista
    hobbista = HobbistaAccount.query.get_or_404(hobbista_id)
    nuovo    = request.form.get('stato')
    try:
        hobbista.stato = StatoHobbista(nuovo)
        db.session.commit()
        flash(f'Stato aggiornato a "{nuovo}" per {hobbista.nome_visualizzato}.', 'success')
    except ValueError:
        flash('Stato non valido.', 'danger')
    return redirect(url_for('admin.artigiani_lista'))


@admin.route('/artigiani/segnalazioni')
@login_required
@admin_required
def artigiani_segnalazioni():
    from app.models.hobbisti import HobbistaSegnalazione
    segnalazioni = (HobbistaSegnalazione.query
                    .filter_by(stato_gestione='da_rivedere')
                    .order_by(HobbistaSegnalazione.data_segnalazione.desc())
                    .all())
    return render_template('admin/artigiani_segnalazioni.html',
                           segnalazioni=segnalazioni)


@admin.route('/artigiani/segnalazioni/<int:seg_id>/gestisci', methods=['POST'])
@login_required
@admin_required
def artigiani_gestisci_segnalazione(seg_id):
    from app.models.hobbisti import HobbistaSegnalazione
    from app.artigiani.utils import elimina_foto_files, ricalcola_storage
    seg    = HobbistaSegnalazione.query.get_or_404(seg_id)
    azione = request.form.get('azione')
    if azione == 'rimuovi':
        foto       = seg.foto
        account_id = foto.account_id
        elimina_foto_files(foto)
        db.session.delete(foto)
        seg.stato_gestione = 'rimosso'
        db.session.commit()
        ricalcola_storage(account_id)
        flash('Foto rimossa.', 'success')
    elif azione == 'ok':
        seg.stato_gestione = 'confermato_ok'
        db.session.commit()
        flash('Segnalazione archiviata come non problematica.', 'success')
    return redirect(url_for('admin.artigiani_segnalazioni'))
