from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, PasswordField
from wtforms.validators import DataRequired, Length, Optional, Email, EqualTo
from flask_login import current_user
from app import db
from app.models import User


class ProfiloForm(FlaskForm):
    nome = StringField('Nome *', validators=[DataRequired(), Length(max=100)])
    cognome = StringField('Cognome *', validators=[DataRequired(), Length(max=100)])
    bio = TextAreaField('Bio', validators=[Optional(), Length(max=500)])


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
