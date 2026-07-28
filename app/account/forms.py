from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, PasswordField, SelectField
from wtforms.validators import DataRequired, Length, Optional, Email, EqualTo
from app.auth.forms import CATEGORIE_PRODOTTI, FASCE_PREZZO
from flask_login import current_user
from app import db
from app.models import User


class ProfiloForm(FlaskForm):
    nome = StringField('Nome *', validators=[DataRequired(), Length(max=100)])
    cognome = StringField('Cognome *', validators=[DataRequired(), Length(max=100)])
    bio = TextAreaField('Bio', validators=[Optional(), Length(max=500)])
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


class CambiaPasswordForm(FlaskForm):
    password_attuale = PasswordField(
        'Password attuale *', validators=[DataRequired()]
    )
    nuova_password = PasswordField(
        'Nuova password *',
        validators=[DataRequired(), Length(min=8, message='Almeno 8 caratteri.')]
    )
    nuova_password2 = PasswordField(
        'Ripeti nuova password *',
        validators=[DataRequired(),
                    EqualTo('nuova_password', message='Le password non coincidono.')]
    )
