from datetime import date
from flask import render_template
from app.models import Mercatino
from app.main import main


@main.route('/')
def index():
    oggi = date.today()

    in_corso = (
        Mercatino.query
        .filter(
            Mercatino.pubblicato == True,
            Mercatino.data_inizio <= oggi,
            Mercatino.data_fine >= oggi,
        )
        .order_by(Mercatino.data_fine.asc())
        .limit(3)
        .all()
    )

    prossimi = (
        Mercatino.query
        .filter(
            Mercatino.pubblicato == True,
            Mercatino.data_inizio > oggi,
        )
        .order_by(Mercatino.data_inizio.asc())
        .limit(6)
        .all()
    )

    totale = Mercatino.query.filter_by(pubblicato=True).count()

    return render_template(
        'main/index.html',
        in_corso=in_corso,
        prossimi=prossimi,
        totale=totale,
    )


@main.app_errorhandler(403)
def forbidden(e):
    return render_template('errors/403.html'), 403


@main.app_errorhandler(404)
def not_found(e):
    return render_template('errors/404.html'), 404


@main.app_errorhandler(500)
def server_error(e):
    return render_template('errors/500.html'), 500
