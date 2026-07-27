import os
from datetime import datetime, timezone
from flask import Flask
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

    # Context processor globale
    @app.context_processor
    def inject_globals():
        return {'current_year': datetime.now(timezone.utc).year}

    # Import modelli per Alembic autogenerate
    with app.app_context():
        from app.models import User, Mercatino, Categoria  # noqa: F401

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

    from app.commands import register_commands
    register_commands(app)

    return app
