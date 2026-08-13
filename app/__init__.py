import sentry_sdk
from sentry_sdk.integrations.flask import FlaskIntegration
import os
from datetime import datetime, timezone
from flask import Flask
from app.extensions import csrf
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_bcrypt import Bcrypt
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_mail import Mail

from config import config

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
bcrypt = Bcrypt()
csrf = CSRFProtect()
limiter = Limiter(key_func=get_remote_address, default_limits=[])
mail = Mail()

login_manager.login_view = 'auth.login'
login_manager.login_message = 'Accedi per vedere questa pagina.'
login_manager.login_message_category = 'warning'


def create_app(config_name=None):
    if config_name is None:
        env = os.environ.get('FLASK_ENV', 'development')
        config_name = 'production' if env == 'production' else 'development'

    app = Flask(__name__)
    app.config.from_object(config[config_name])

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    bcrypt.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)
    mail.init_app(app)

    # Artigiani hobbisti upload config
    import os as _os
    app.config.setdefault(
        'ARTIGIANI_UPLOAD_FOLDER',
        _os.path.join(app.root_path, 'static', 'uploads', 'artigiani')
    )
    app.config.setdefault('ARTIGIANI_UPLOAD_STATIC_REL', 'uploads/artigiani')

    # Context processor globale
    @app.context_processor
    def inject_globals():
        return {'current_year': datetime.now(timezone.utc).year}

    # Import modelli per Alembic autogenerate
    with app.app_context():
        from app.models import User, Mercatino, Categoria, Recensione, Preferito, Alert  # noqa: F401
        from app.models.hobbisti import (  # noqa: F401
            HobbistaAccount, HobbistaFoto, HobbistaPiano,
            HobbistaAbbonamento, HobbistaSegnalazione
        )
        from app.models.follow import (  # noqa: F401
            HobbistaFollow, HobbistaEventoPartecipazione, HobbistaFotoDigestQueue
        )

    from app.main import main as main_bp
    app.register_blueprint(main_bp)

    from app.auth import auth as auth_bp
    app.register_blueprint(auth_bp, url_prefix='/auth')

    from app.mercatini import mercatini as mercatini_bp
    app.register_blueprint(mercatini_bp, url_prefix='/mercatini')

    from app.account import account as account_bp
    app.register_blueprint(account_bp, url_prefix='/account')

    from app.admin import admin as admin_bp
    app.register_blueprint(admin_bp, url_prefix='/admin')

    from app.chat import chat as chat_bp
    app.register_blueprint(chat_bp, url_prefix='/chat')

    # abbonamento blueprint rimosso — servizio gratuito
    # from app.abbonamento import abbonamento as abbonamento_bp
    # app.register_blueprint(abbonamento_bp, url_prefix='/abbonamento')

    from app.artigiani_auth import artigiani_auth as artigiani_auth_bp
    app.register_blueprint(artigiani_auth_bp, url_prefix='/artigiani/auth')

    from app.artigiani import artigiani as artigiani_bp
    app.register_blueprint(artigiani_bp, url_prefix='/artigiani')

    from app.commands import register_commands
    register_commands(app)

    # Scheduler APScheduler (avvia in produzione)
    import os as _os
    if _os.environ.get('FLASK_ENV') == 'production':
        from app.scheduler import init_scheduler
        init_scheduler(app)




    # ── CLI: crea Stripe Prices per piani hobbisti ──────────────────────────
    @app.cli.command('seed-hobbisti-stripe')
    def seed_hobbisti_stripe():
        """Crea i Stripe Products/Prices per i piani hobbisti."""
        import stripe as _stripe
        _stripe.api_key = app.config['STRIPE_SECRET_KEY']
        with app.app_context():
            from app.models.hobbisti import HobbistaPiano
            piani = HobbistaPiano.query.filter_by(attivo=True).all()
            for piano in piani:
                if piano.stripe_price_id:
                    print(f'  {piano.nome}: gia configurato ({piano.stripe_price_id})')
                    continue
                product = _stripe.Product.create(
                    name=f'mercatini.blog — Piano Artigiani {piano.nome}',
                    metadata={'hobbista_piano_id': str(piano.id)},
                )
                price = _stripe.Price.create(
                    product=product.id,
                    unit_amount=int(piano.prezzo_mensile_eur * 100),
                    currency='eur',
                    recurring={'interval': 'month'},
                    nickname=f'Piano {piano.nome} mensile',
                )
                piano.stripe_price_id = price.id
                db.session.commit()
                print(f'  {piano.nome}: price_id={price.id}')
            print('Seed completato.')


    with app.app_context():
        for vn in ["artigiani.stripe_webhook_hobbisti","subscription.stripe_webhook"]:
            vf = app.view_functions.get(vn)
            if vf: csrf.exempt(vf)

    return app
