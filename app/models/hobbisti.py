"""
app/models/hobbisti.py
Modelli per la sezione Artigiani Hobbisti di mercatini.blog.
VETRINA SOLO — nessun flusso di acquisto/pagamento tra utenti.
"""
import enum
from datetime import datetime, timezone
from app import db


class StatoHobbista(enum.Enum):
    in_verifica = 'in_verifica'
    attivo      = 'attivo'
    sospeso     = 'sospeso'


class StatoAbbonamento(enum.Enum):
    attivo     = 'attivo'
    scaduto    = 'scaduto'
    cancellato = 'cancellato'


# ── Piani ────────────────────────────────────────────────────────────────────

class HobbistaPiano(db.Model):
    __tablename__ = 'hobbista_piani'

    id                 = db.Column(db.Integer, primary_key=True)
    nome               = db.Column(db.String(50), nullable=False)
    prezzo_mensile_eur = db.Column(db.Numeric(6, 2), nullable=False)
    storage_max_mb     = db.Column(db.Integer, nullable=False)
    attivo             = db.Column(db.Boolean, nullable=False, default=True)
    stripe_price_id    = db.Column(db.String(100), nullable=True)

    def __repr__(self):
        return f'<HobbistaPiano {self.nome}>'


# ── Account ───────────────────────────────────────────────────────────────────

class HobbistaAccount(db.Model):
    __tablename__ = 'hobbista_accounts'

    id                   = db.Column(db.Integer, primary_key=True)
    nome_visualizzato    = db.Column(db.String(100), nullable=False)
    email                = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash        = db.Column(db.String(255), nullable=True)   # nullable: OAuth
    google_id            = db.Column(db.String(100), nullable=True, unique=True)
    instagram_handle     = db.Column(db.String(100), nullable=True)
    whatsapp_number      = db.Column(db.String(30), nullable=True)
    telegram_handle      = db.Column(db.String(100), nullable=True)
    bio_breve            = db.Column(db.String(200), nullable=True)
    comune               = db.Column(db.String(100), nullable=True)
    data_registrazione   = db.Column(
        db.DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )
    stato                = db.Column(
        db.Enum(StatoHobbista, name='stato_hobbista'),
        nullable=False, default=StatoHobbista.in_verifica
    )
    piano_id             = db.Column(
        db.Integer, db.ForeignKey('hobbista_piani.id'), nullable=True
    )
    stripe_customer_id   = db.Column(db.String(100), nullable=True, unique=True, index=True)
    storage_usato_mb     = db.Column(db.Float, nullable=False, default=0.0)
    email_verificata     = db.Column(db.Boolean, nullable=False, default=False)
    email_verify_token   = db.Column(db.String(100), nullable=True, unique=True)
    ultimo_accesso       = db.Column(db.DateTime(timezone=True), nullable=True)
    termini_accettati_il = db.Column(db.DateTime(timezone=True), nullable=True)

    # Relationships
    piano = db.relationship('HobbistaPiano', backref='accounts')
    foto  = db.relationship(
        'HobbistaFoto', back_populates='account',
        cascade='all, delete-orphan',
        order_by='HobbistaFoto.ordine'
    )

    def __repr__(self):
        return f'<HobbistaAccount {self.email}>'

    @property
    def storage_max_mb(self):
        return self.piano.storage_max_mb if self.piano else 500

    @property
    def storage_percentuale(self):
        mx = self.storage_max_mb
        if mx == 0:
            return 0
        return min(100, round(self.storage_usato_mb / mx * 100, 1))

    @property
    def whatsapp_url(self):
        if not self.whatsapp_number:
            return None
        numero = ''.join(c for c in self.whatsapp_number if c.isdigit() or c == '+')
        return f"https://wa.me/{numero.lstrip('+')}"

    @property
    def instagram_url(self):
        if not self.instagram_handle:
            return None
        handle = self.instagram_handle.lstrip('@')
        return f"https://instagram.com/{handle}"

    @property
    def foto_di_copertina(self):
        return self.foto[0] if self.foto else None

    @property
    def abbonamento_attivo(self):
        return next(
            (a for a in self.abbonamenti if a.stato == StatoAbbonamento.attivo), None
        )


# ── Foto ─────────────────────────────────────────────────────────────────────

class HobbistaFoto(db.Model):
    __tablename__ = 'hobbista_foto'

    id               = db.Column(db.Integer, primary_key=True)
    account_id       = db.Column(
        db.Integer,
        db.ForeignKey('hobbista_accounts.id', ondelete='CASCADE'),
        nullable=False, index=True
    )
    filename         = db.Column(db.String(255), nullable=False)
    path_relativo    = db.Column(db.String(500), nullable=False)
    didascalia       = db.Column(db.String(150), nullable=True)
    dimensione_kb    = db.Column(db.Integer, nullable=False, default=0)
    data_caricamento = db.Column(
        db.DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )
    ordine           = db.Column(db.Integer, nullable=False, default=0)

    account = db.relationship('HobbistaAccount', back_populates='foto')

    def __repr__(self):
        return f'<HobbistaFoto {self.filename}>'

    @property
    def url(self):
        return f"/static/{self.path_relativo}"

    @property
    def thumb_url(self):
        # path_relativo: uploads/artigiani/<id>/<file>.jpg
        # thumb:         uploads/artigiani/<id>/thumb/<file>.jpg
        parts = self.path_relativo.rsplit('/', 1)
        if len(parts) == 2:
            return f"/static/{parts[0]}/thumb/{parts[1]}"
        return self.url


# ── Abbonamento (storico) ─────────────────────────────────────────────────────

class HobbistaAbbonamento(db.Model):
    __tablename__ = 'hobbista_abbonamenti'

    id                 = db.Column(db.Integer, primary_key=True)
    account_id         = db.Column(db.Integer, db.ForeignKey('hobbista_accounts.id'), nullable=False)
    piano_id           = db.Column(db.Integer, db.ForeignKey('hobbista_piani.id'), nullable=False)
    data_inizio        = db.Column(db.DateTime(timezone=True), nullable=False)
    data_scadenza      = db.Column(db.DateTime(timezone=True), nullable=False)
    stato              = db.Column(
        db.Enum(StatoAbbonamento, name='stato_abbonamento'),
        nullable=False, default=StatoAbbonamento.attivo
    )
    provider_pagamento      = db.Column(db.String(50), nullable=True)
    stripe_subscription_id  = db.Column(db.String(100), nullable=True, index=True)
    stripe_session_id       = db.Column(db.String(200), nullable=True)

    account = db.relationship('HobbistaAccount', backref='abbonamenti')
    piano   = db.relationship('HobbistaPiano')

    def __repr__(self):
        return f'<HobbistaAbbonamento acc={self.account_id}>'


# ── Segnalazioni ──────────────────────────────────────────────────────────────

class HobbistaSegnalazione(db.Model):
    __tablename__ = 'hobbista_segnalazioni'

    id                = db.Column(db.Integer, primary_key=True)
    foto_id           = db.Column(db.Integer, db.ForeignKey('hobbista_foto.id'), nullable=False)
    motivo            = db.Column(db.String(500), nullable=False)
    data_segnalazione = db.Column(
        db.DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )
    stato_gestione    = db.Column(db.String(20), nullable=False, default='da_rivedere')
    # valori: 'da_rivedere', 'rimosso', 'confermato_ok'

    foto = db.relationship('HobbistaFoto', backref='segnalazioni')

    def __repr__(self):
        return f'<HobbistaSegnalazione foto={self.foto_id}>'
