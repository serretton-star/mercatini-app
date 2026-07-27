import secrets
from datetime import datetime, timezone, timedelta
from flask_login import UserMixin
from app import db, login_manager


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    nome = db.Column(db.String(100), nullable=False)
    cognome = db.Column(db.String(100), nullable=False)
    bio = db.Column(db.Text, nullable=True)
    ruolo = db.Column(db.String(20), nullable=False, default='espositore')
    # ruolo: 'espositore' | 'organizzatore' | 'admin'
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    # Password reset
    reset_token = db.Column(db.String(100), nullable=True, unique=True, index=True)
    reset_token_expires = db.Column(db.DateTime(timezone=True), nullable=True)

    created_at = db.Column(
        db.DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )
    updated_at = db.Column(
        db.DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )

    def __repr__(self):
        return f'<User {self.email}>'

    @property
    def nome_completo(self):
        return f'{self.nome} {self.cognome}'

    @property
    def is_admin(self):
        return self.ruolo == 'admin'

    def genera_reset_token(self, expires_hours=1):
        """Genera un token sicuro per il reset password (valido N ore)."""
        self.reset_token = secrets.token_urlsafe(32)
        self.reset_token_expires = datetime.now(timezone.utc) + timedelta(hours=expires_hours)
        return self.reset_token

    def reset_token_valido(self):
        """True se il token esiste e non è scaduto."""
        if not self.reset_token or not self.reset_token_expires:
            return False
        return datetime.now(timezone.utc) < self.reset_token_expires

    def cancella_reset_token(self):
        self.reset_token = None
        self.reset_token_expires = None
