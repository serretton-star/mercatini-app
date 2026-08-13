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
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    provincia_residenza = db.Column(db.String(5), nullable=True, index=True)
    categoria_prodotti  = db.Column(db.String(50), nullable=True)  # profilo espositore
    fascia_prezzo       = db.Column(db.String(20), nullable=True)  # fascia prezzo prodotti
    notifiche_email = db.Column(db.Boolean, nullable=False, default=True)
    # Preferenze notifiche artigiani hobbisti
    notifiche_eventi_hobbisti      = db.Column(db.Boolean, nullable=False, default=True)
    notifiche_digest_foto_hobbisti = db.Column(db.Boolean, nullable=False, default=True)

    # GDPR consent
    privacy_accepted = db.Column(db.Boolean, nullable=False, default=False)
    privacy_accepted_at = db.Column(db.DateTime(timezone=True), nullable=True)

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
        self.reset_token = secrets.token_urlsafe(32)
        self.reset_token_expires = datetime.now(timezone.utc) + timedelta(hours=expires_hours)
        return self.reset_token

    def reset_token_valido(self):
        if not self.reset_token or not self.reset_token_expires:
            return False
        return datetime.now(timezone.utc) < self.reset_token_expires

    def cancella_reset_token(self):
        self.reset_token = None
        self.reset_token_expires = None

    def genera_verify_token(self):
        self.email_verify_token = secrets.token_urlsafe(32)
        return self.email_verify_token

    def conferma_email(self):
        self.email_verified = True
        self.email_verify_token = None

    # Email verification
    email_verified       = db.Column(db.Boolean, nullable=False, default=False)
    email_verify_token   = db.Column(db.String(100), nullable=True, unique=True, index=True)

    # Stripe
    stripe_customer_id = db.Column(db.String(100), nullable=True, unique=True, index=True)
    subscription_end   = db.Column(db.DateTime(timezone=True), nullable=True)

    @property
    def is_premium(self):
        from datetime import datetime, timezone
        if self.ruolo == 'admin':
            return True
        if self.subscription_end is None:
            return False
        return datetime.now(timezone.utc) < self.subscription_end
    # Chat AI usage tracking
    subscription_plan = db.Column(db.String(10), nullable=True)   # '1m','3m','6m','12m'
    ai_chat_count     = db.Column(db.Integer,    nullable=False, default=0)
    ai_chat_reset     = db.Column(db.DateTime(timezone=True), nullable=True)

    _CHAT_LIMITS = {'trial': 10, '1m': 5, '3m': 10, '6m': 15, '12m': 20}

    @property
    def chat_limit(self):
        return self._CHAT_LIMITS.get(self.subscription_plan or '', 5)

    def can_chat(self):
        """Chat illimitata per tutti gli utenti."""
        return True, 0, 0

    def increment_chat(self):
        """Incrementa il contatore mensile chat AI."""
        now = datetime.now(timezone.utc)
        if (self.ai_chat_reset is None
                or now.month != self.ai_chat_reset.month
                or now.year  != self.ai_chat_reset.year):
            self.ai_chat_count = 0
            self.ai_chat_reset = now
        self.ai_chat_count += 1
        db.session.commit()

