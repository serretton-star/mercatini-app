from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField, SelectField
from wtforms.validators import (
    DataRequired, Email, Length, EqualTo, Optional, ValidationError
)
from app.models.user import User

PROVINCE_ITALIANE = [
    ('', '— Seleziona provincia —'),
    ('AG', 'Agrigento (AG)'), ('AL', 'Alessandria (AL)'), ('AN', 'Ancona (AN)'),
    ('AO', 'Aosta (AO)'), ('AR', 'Arezzo (AR)'), ('AP', 'Ascoli Piceno (AP)'),
    ('AT', 'Asti (AT)'), ('AV', 'Avellino (AV)'), ('BA', 'Bari (BA)'),
    ('BT', 'Barletta-Andria-Trani (BT)'), ('BL', 'Belluno (BL)'),
    ('BN', 'Benevento (BN)'), ('BG', 'Bergamo (BG)'), ('BI', 'Biella (BI)'),
    ('BO', 'Bologna (BO)'), ('BZ', 'Bolzano (BZ)'), ('BS', 'Brescia (BS)'),
    ('BR', 'Brindisi (BR)'), ('CA', 'Cagliari (CA)'), ('CL', 'Caltanissetta (CL)'),
    ('CB', 'Campobasso (CB)'), ('CI', 'Carbonia-Iglesias (CI)'),
    ('CE', 'Caserta (CE)'), ('CT', 'Catania (CT)'), ('CZ', 'Catanzaro (CZ)'),
    ('CH', 'Chieti (CH)'), ('CO', 'Como (CO)'), ('CS', 'Cosenza (CS)'),
    ('CR', 'Cremona (CR)'), ('KR', 'Crotone (KR)'), ('CN', 'Cuneo (CN)'),
    ('EN', 'Enna (EN)'), ('FM', 'Fermo (FM)'), ('FE', 'Ferrara (FE)'),
    ('FI', 'Firenze (FI)'), ('FG', 'Foggia (FG)'), ('FC', 'Forlì-Cesena (FC)'),
    ('FR', 'Frosinone (FR)'), ('GE', 'Genova (GE)'), ('GO', 'Gorizia (GO)'),
    ('GR', 'Grosseto (GR)'), ('IM', 'Imperia (IM)'), ('IS', 'Isernia (IS)'),
    ('SP', 'La Spezia (SP)'), ('AQ', "L'Aquila (AQ)"), ('LT', 'Latina (LT)'),
    ('LE', 'Lecce (LE)'), ('LC', 'Lecco (LC)'), ('LI', 'Livorno (LI)'),
    ('LO', 'Lodi (LO)'), ('LU', 'Lucca (LU)'), ('MC', 'Macerata (MC)'),
    ('MN', 'Mantova (MN)'), ('MS', 'Massa-Carrara (MS)'), ('MT', 'Matera (MT)'),
    ('VS', 'Medio Campidano (VS)'), ('ME', 'Messina (ME)'), ('MI', 'Milano (MI)'),
    ('MO', 'Modena (MO)'), ('MB', 'Monza e Brianza (MB)'), ('NA', 'Napoli (NA)'),
    ('NO', 'Novara (NO)'), ('NU', 'Nuoro (NU)'), ('OG', 'Ogliastra (OG)'),
    ('OT', 'Olbia-Tempio (OT)'), ('OR', 'Oristano (OR)'), ('PD', 'Padova (PD)'),
    ('PA', 'Palermo (PA)'), ('PR', 'Parma (PR)'), ('PV', 'Pavia (PV)'),
    ('PG', 'Perugia (PG)'), ('PU', 'Pesaro e Urbino (PU)'), ('PE', 'Pescara (PE)'),
    ('PC', 'Piacenza (PC)'), ('PI', 'Pisa (PI)'), ('PT', 'Pistoia (PT)'),
    ('PN', 'Pordenone (PN)'), ('PZ', 'Potenza (PZ)'), ('PO', 'Prato (PO)'),
    ('RG', 'Ragusa (RG)'), ('RA', 'Ravenna (RA)'), ('RC', 'Reggio Calabria (RC)'),
    ('RE', 'Reggio Emilia (RE)'), ('RI', 'Rieti (RI)'), ('RN', 'Rimini (RN)'),
    ('RM', 'Roma (RM)'), ('RO', 'Rovigo (RO)'), ('SA', 'Salerno (SA)'),
    ('SS', 'Sassari (SS)'), ('SV', 'Savona (SV)'), ('SI', 'Siena (SI)'),
    ('SR', 'Siracusa (SR)'), ('SO', 'Sondrio (SO)'), ('TA', 'Taranto (TA)'),
    ('TE', 'Teramo (TE)'), ('TR', 'Terni (TR)'), ('TO', 'Torino (TO)'),
    ('TP', 'Trapani (TP)'), ('TN', 'Trento (TN)'), ('TV', 'Treviso (TV)'),
    ('TS', 'Trieste (TS)'), ('UD', 'Udine (UD)'), ('VA', 'Varese (VA)'),
    ('VE', 'Venezia (VE)'), ('VB', 'Verbano-Cusio-Ossola (VB)'),
    ('VC', 'Vercelli (VC)'), ('VR', 'Verona (VR)'), ('VV', 'Vibo Valentia (VV)'),
    ('VI', 'Vicenza (VI)'), ('VT', 'Viterbo (VT)'),
]


CATEGORIE_PRODOTTI = [
    ('', '— Seleziona categoria —'),
    ('artigianato', 'Artigianato'),
    ('vintage', 'Vintage & Retro'),
    ('usato', 'Usato & Seconda mano'),
    ('cibo', 'Cibo e Bevande'),
    ('gioielli', 'Gioielli & Bigiotteria'),
    ('abbigliamento', 'Abbigliamento'),
    ('ceramica', 'Ceramica & Porcellana'),
    ('decorazioni', 'Decorazioni & Home'),
    ('libri', 'Libri & Fumetti'),
    ('arte', 'Arte & Quadri'),
    ('piante', 'Piante & Fiori'),
    ('giocattoli', 'Giocattoli'),
    ('altro', 'Altro'),
]

FASCE_PREZZO = [
    ('', '— Seleziona fascia —'),
    ('0-20', 'fino a €20'),
    ('20-50', '€20 – €50'),
    ('50-100', '€50 – €100'),
    ('100-300', '€100 – €300'),
    ('300+', 'oltre €300'),
]


class RegistrationForm(FlaskForm):
    nome = StringField(
        'Nome',
        validators=[DataRequired(message='Il nome è obbligatorio.'),
                    Length(min=2, max=100)]
    )
    cognome = StringField(
        'Cognome',
        validators=[DataRequired(message='Il cognome è obbligatorio.'),
                    Length(min=2, max=100)]
    )
    email = StringField(
        'Email',
        validators=[DataRequired(), Email(message='Email non valida.'),
                    Length(max=255)]
    )
    password = PasswordField(
        'Password',
        validators=[DataRequired(),
                    Length(min=8, message='Minimo 8 caratteri.')]
    )
    password2 = PasswordField(
        'Conferma password',
        validators=[DataRequired(),
                    EqualTo('password', message='Le password non coincidono.')]
    )
    provincia_residenza = SelectField(
        'Provincia di residenza',
        choices=PROVINCE_ITALIANE,
        validators=[Optional()],
        default=''
    )
    categoria_prodotti = SelectField(
        'Cosa vendi principalmente?',
        choices=CATEGORIE_PRODOTTI,
        validators=[Optional()],
        default=''
    )
    fascia_prezzo = SelectField(
        'Fascia di prezzo media dei tuoi prodotti',
        choices=FASCE_PREZZO,
        validators=[Optional()],
        default=''
    )
    notifiche_email = BooleanField(
        'Inviami email quando ci sono nuovi mercatini nella mia provincia',
        default=True
    )
    consenso_privacy = BooleanField(
        'Ho letto e accetto la Privacy Policy',
        validators=[DataRequired(message='Devi accettare la Privacy Policy.')]
    )
    submit = SubmitField('Registrati')

    def validate_email(self, field):
        if User.query.filter_by(email=field.data.lower().strip()).first():
            raise ValidationError('Questa email è già registrata.')


class LoginForm(FlaskForm):
    email = StringField(
        'Email',
        validators=[DataRequired(), Email()]
    )
    password = PasswordField(
        'Password',
        validators=[DataRequired()]
    )
    remember_me = BooleanField('Ricordami')
    submit = SubmitField('Accedi')


class ForgotPasswordForm(FlaskForm):
    email = StringField(
        'Email',
        validators=[DataRequired(), Email(message='Email non valida.'), Length(max=255)]
    )
    submit = SubmitField('Invia link di reset')


class ResetPasswordForm(FlaskForm):
    password = PasswordField(
        'Nuova password',
        validators=[DataRequired(), Length(min=8, message='Minimo 8 caratteri.')]
    )
    password2 = PasswordField(
        'Conferma password',
        validators=[DataRequired(), EqualTo('password', message='Le password non coincidono.')]
    )
    submit = SubmitField('Reimposta password')
