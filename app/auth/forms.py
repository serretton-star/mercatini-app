from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField
from wtforms.validators import (
    DataRequired, Email, Length, EqualTo, ValidationError
)
from app.models.user import User


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
