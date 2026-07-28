from datetime import datetime, timezone
from slugify import slugify
from app import db


mercatino_categorie = db.Table(
    'mercatino_categorie',
    db.Column('mercatino_id', db.Integer, db.ForeignKey('mercatini.id'), primary_key=True),
    db.Column('categoria_id', db.Integer, db.ForeignKey('categorie.id'), primary_key=True),
)


class Categoria(db.Model):
    __tablename__ = 'categorie'
    id   = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), unique=True, nullable=False)
    slug = db.Column(db.String(100), unique=True, nullable=False)

    def __init__(self, nome):
        self.nome = nome
        self.slug = slugify(nome)

    def __repr__(self):
        return f'<Categoria {self.nome}>'


class Mercatino(db.Model):
    __tablename__ = 'mercatini'
    id           = db.Column(db.Integer, primary_key=True)
    titolo       = db.Column(db.String(200), nullable=False)
    descrizione  = db.Column(db.Text, nullable=True)
    citta        = db.Column(db.String(100), nullable=False, index=True)
    regione      = db.Column(db.String(100), nullable=False, index=True)
    provincia    = db.Column(db.String(5), nullable=True)
    indirizzo    = db.Column(db.String(255), nullable=True)
    lat          = db.Column(db.Numeric(10, 7), nullable=True)
    lon          = db.Column(db.Numeric(10, 7), nullable=True)
    data_inizio  = db.Column(db.Date, nullable=False, index=True)
    data_fine    = db.Column(db.Date, nullable=False)
    orario       = db.Column(db.String(100), nullable=True)
    sito_web     = db.Column(db.String(500), nullable=True)
    telefono     = db.Column(db.String(30), nullable=True)
    email_contatto    = db.Column(db.String(255), nullable=True)
    ingresso_gratuito = db.Column(db.Boolean, nullable=False, default=True)
    prezzo_ingresso   = db.Column(db.Numeric(6, 2), nullable=True)
    numero_espositori = db.Column(db.Integer, nullable=True)
    pubblicato   = db.Column(db.Boolean, nullable=False, default=False, index=True)
    fonte_crawler = db.Column(db.String(500), nullable=True)
    created_at   = db.Column(db.DateTime(timezone=True), nullable=False,
                             default=lambda: datetime.now(timezone.utc))
    updated_at   = db.Column(db.DateTime(timezone=True), nullable=False,
                             default=lambda: datetime.now(timezone.utc),
                             onupdate=lambda: datetime.now(timezone.utc))
    organizzatore_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    organizzatore = db.relationship('User', backref=db.backref('mercatini', lazy='dynamic'))
    categorie = db.relationship('Categoria', secondary=mercatino_categorie,
                                backref=db.backref('mercatini', lazy='dynamic'), lazy='subquery')

    @property
    def is_futuro(self):
        return self.data_inizio >= datetime.now(timezone.utc).date()

    @property
    def is_in_corso(self):
        oggi = datetime.now(timezone.utc).date()
        return self.data_inizio <= oggi <= self.data_fine

    @property
    def durata_giorni(self):
        return (self.data_fine - self.data_inizio).days + 1

    @property
    def prezzo_display(self):
        if self.ingresso_gratuito:
            return 'Gratuito'
        if self.prezzo_ingresso:
            return f'\u20ac{self.prezzo_ingresso:.2f}'
        return 'A pagamento'

    @property
    def voto_medio(self):
        recensioni = [r for r in self.recensioni if r.approvata]
        if not recensioni:
            return None
        return round(sum(r.voto for r in recensioni) / len(recensioni), 1)

    @property
    def num_recensioni(self):
        return sum(1 for r in self.recensioni if r.approvata)

    def __repr__(self):
        return f'<Mercatino {self.titolo} ({self.citta})>'


class Recensione(db.Model):
    __tablename__ = 'recensioni'
    __table_args__ = (db.UniqueConstraint('user_id', 'mercatino_id', name='uq_recensione_utente'),)

    id           = db.Column(db.Integer, primary_key=True)
    user_id      = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    mercatino_id = db.Column(db.Integer, db.ForeignKey('mercatini.id'), nullable=False, index=True)
    voto         = db.Column(db.Integer, nullable=False)   # 1-5
    testo        = db.Column(db.Text, nullable=False)
    approvata    = db.Column(db.Boolean, nullable=False, default=False)
    created_at   = db.Column(db.DateTime(timezone=True), nullable=False,
                             default=lambda: datetime.now(timezone.utc))

    utente    = db.relationship('User',      backref=db.backref('recensioni',  lazy='dynamic'))
    mercatino = db.relationship('Mercatino', backref=db.backref('recensioni',  lazy='dynamic'))

    def __repr__(self):
        return f'<Recensione {self.voto}/5 su {self.mercatino_id}>'


class Preferito(db.Model):
    __tablename__ = 'preferiti'
    __table_args__ = (db.UniqueConstraint('user_id', 'mercatino_id', name='uq_preferito_utente'),)

    id           = db.Column(db.Integer, primary_key=True)
    user_id      = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    mercatino_id = db.Column(db.Integer, db.ForeignKey('mercatini.id'), nullable=False, index=True)
    created_at   = db.Column(db.DateTime(timezone=True), nullable=False,
                             default=lambda: datetime.now(timezone.utc))

    utente    = db.relationship('User',      backref=db.backref('preferiti',   lazy='dynamic'))
    mercatino = db.relationship('Mercatino', backref=db.backref('preferiti',   lazy='dynamic'))


class Alert(db.Model):
    __tablename__ = 'alerts'

    id              = db.Column(db.Integer, primary_key=True)
    user_id         = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    parole_chiave   = db.Column(db.String(200), nullable=True)
    provincia       = db.Column(db.String(5),   nullable=True)
    categoria_id    = db.Column(db.Integer, db.ForeignKey('categorie.id'), nullable=True)
    attivo          = db.Column(db.Boolean, nullable=False, default=True)
    ultima_notifica_il = db.Column(db.Date, nullable=True)
    created_at      = db.Column(db.DateTime(timezone=True), nullable=False,
                                default=lambda: datetime.now(timezone.utc))

    utente    = db.relationship('User',      backref=db.backref('alerts',     lazy='dynamic'))
    categoria = db.relationship('Categoria')
