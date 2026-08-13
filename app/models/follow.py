"""
app/models/follow.py
Modelli per il sistema follow artigiani hobbisti su mercatini.blog.
"""
from datetime import datetime, timezone
from app import db


class HobbistaFollow(db.Model):
    """Relazione follower (User espositore) → artigiano (HobbistaAccount)."""
    __tablename__ = 'hobbista_follow'
    __table_args__ = (
        db.UniqueConstraint('user_id', 'hobbista_id', name='uq_follow_user_hobbista'),
    )

    id                 = db.Column(db.Integer, primary_key=True)
    user_id            = db.Column(
        db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'),
        nullable=False, index=True
    )
    hobbista_id        = db.Column(
        db.Integer, db.ForeignKey('hobbista_accounts.id', ondelete='CASCADE'),
        nullable=False, index=True
    )
    data_inizio_follow = db.Column(
        db.DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )
    attivo             = db.Column(db.Boolean, nullable=False, default=True)

    user     = db.relationship('User',
                               backref=db.backref('follow_hobbisti', lazy='dynamic'))
    hobbista = db.relationship('HobbistaAccount',
                               backref=db.backref('followers', lazy='dynamic'))

    def __repr__(self):
        return f'<HobbistaFollow user={self.user_id} hobbista={self.hobbista_id}>'


class HobbistaEventoPartecipazione(db.Model):
    """Dichiarazione di partecipazione di un artigiano a un mercatino/evento."""
    __tablename__ = 'hobbista_evento_partecipazione'

    id                 = db.Column(db.Integer, primary_key=True)
    hobbista_id        = db.Column(
        db.Integer, db.ForeignKey('hobbista_accounts.id', ondelete='CASCADE'),
        nullable=False, index=True
    )
    # FK al mercatino in catalogo (nullable — fallback testuale se non in catalogo)
    mercatino_id       = db.Column(
        db.Integer, db.ForeignKey('mercatini.id', ondelete='SET NULL'),
        nullable=True
    )
    # Campi testuali fallback (usati quando mercatino_id is None)
    nome_evento        = db.Column(db.String(200), nullable=True)
    data_evento        = db.Column(db.Date, nullable=True)
    luogo_evento       = db.Column(db.String(200), nullable=True)
    #
    data_dichiarazione = db.Column(
        db.DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )
    messaggio_breve    = db.Column(db.String(200), nullable=True)
    notifica_inviata   = db.Column(db.Boolean, nullable=False, default=False)

    hobbista  = db.relationship('HobbistaAccount',
                                backref=db.backref('partecipazioni', lazy='dynamic'))
    mercatino = db.relationship('Mercatino',
                                backref=db.backref('partecipazioni_artigiani', lazy='dynamic'))

    @property
    def nome_evento_display(self):
        return self.mercatino.titolo if self.mercatino else (self.nome_evento or 'Evento')

    @property
    def data_evento_display(self):
        return self.mercatino.data_inizio if self.mercatino else self.data_evento

    @property
    def luogo_display(self):
        if self.mercatino:
            return f'{self.mercatino.citta}, {self.mercatino.regione}'
        return self.luogo_evento or ''

    def __repr__(self):
        return f'<HobbistaEventoPartecipazione hobbista={self.hobbista_id}>'


class HobbistaFotoDigestQueue(db.Model):
    """Coda foto in attesa del prossimo digest giornaliero."""
    __tablename__ = 'hobbista_foto_digest_queue'

    id                = db.Column(db.Integer, primary_key=True)
    foto_id           = db.Column(
        db.Integer, db.ForeignKey('hobbista_foto.id', ondelete='CASCADE'),
        nullable=False, index=True
    )
    hobbista_id       = db.Column(
        db.Integer, db.ForeignKey('hobbista_accounts.id', ondelete='CASCADE'),
        nullable=False, index=True
    )
    creato_il         = db.Column(
        db.DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc)
    )
    inclusa_in_digest = db.Column(db.Boolean, nullable=False, default=False, index=True)

    foto     = db.relationship('HobbistaFoto',
                               backref=db.backref('digest_queue_entry', uselist=False))
    hobbista = db.relationship('HobbistaAccount',
                               backref=db.backref('foto_digest_queue', lazy='dynamic'))

    def __repr__(self):
        return f'<HobbistaFotoDigestQueue foto={self.foto_id}>'
