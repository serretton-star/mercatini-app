from datetime import date
from flask import render_template
from app.models import Mercatino
from app.models.user import User
from app.main import main


@main.route('/sw.js')
def service_worker():
    import os
    from flask import send_from_directory, make_response, current_app
    static_dir = os.path.join(current_app.root_path, 'static')
    resp = make_response(send_from_directory(static_dir, 'sw.js'))
    resp.headers['Service-Worker-Allowed'] = '/'
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    resp.headers['Expires'] = '0'
    resp.headers['Content-Type'] = 'application/javascript'
    return resp


@main.route('/')
def index():
    oggi = date.today()
    in_corso = (
        Mercatino.query
        .filter(Mercatino.pubblicato == True,
                Mercatino.data_inizio <= oggi,
                Mercatino.data_fine >= oggi)
        .order_by(Mercatino.data_fine.asc()).limit(3).all()
    )
    prossimi = (
        Mercatino.query
        .filter(Mercatino.pubblicato == True,
                Mercatino.data_inizio > oggi)
        .order_by(Mercatino.data_inizio.asc()).limit(6).all()
    )
    totale = Mercatino.query.filter_by(pubblicato=True).count()
    utenti = User.query.count()
    # Artigiani hobbisti in vetrina
    try:
        from app.models.hobbisti import HobbistaAccount, StatoHobbista
        hobbisti_attivi = (
            HobbistaAccount.query
            .filter_by(stato=StatoHobbista.attivo)
            .order_by(HobbistaAccount.data_registrazione.desc())
            .limit(6).all()
        )
    except Exception:
        hobbisti_attivi = []
    return render_template('main/index.html',
                           in_corso=in_corso, prossimi=prossimi,
                           totale=totale, utenti=utenti,
                           hobbisti_attivi=hobbisti_attivi)


@main.route('/privacy')
def privacy():
    return render_template('main/privacy.html')


@main.app_errorhandler(403)
def forbidden(e):
    return render_template('errors/403.html'), 403

@main.app_errorhandler(404)
def not_found(e):
    return render_template('errors/404.html'), 404

@main.app_errorhandler(500)
def server_error(e):
    return render_template('errors/500.html'), 500


@main.route('/landing')
def landing():
    from flask import request as _req
    try:
        from app.models.landing import LandingVisit
        LandingVisit.log_visit(_req)
    except Exception:
        pass
        # Primo artigiano attivo per card landing
    try:
        from app.models.hobbisti import HobbistaAccount, StatoHobbista
        primo_artigiano = (
            HobbistaAccount.query
            .filter_by(stato=StatoHobbista.attivo)
            .order_by(HobbistaAccount.data_registrazione.desc())
            .first()
        )
    except Exception:
        primo_artigiano = None
    return render_template('main/landing.html',
                           primo_artigiano=primo_artigiano)
