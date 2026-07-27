from datetime import date
from flask_wtf import FlaskForm
from wtforms import (
    StringField, TextAreaField, DateField, BooleanField,
    DecimalField, IntegerField, SelectMultipleField, widgets
)
from wtforms.validators import (
    DataRequired, Length, Optional, URL, NumberRange,
    ValidationError, Email
)


class MultiCheckboxField(SelectMultipleField):
    """Checkbox multipli per le categorie."""
    widget = widgets.ListWidget(prefix_label=False)
    option_widget = widgets.CheckboxInput()


class MercatinoForm(FlaskForm):
    titolo = StringField(
        'Titolo *',
        validators=[DataRequired(message='Il titolo è obbligatorio.'),
                    Length(max=200)]
    )
    descrizione = TextAreaField(
        'Descrizione',
        validators=[Optional(), Length(max=5000)]
    )
    citta = StringField(
        'Città *',
        validators=[DataRequired(message='La città è obbligatoria.'), Length(max=100)]
    )
    regione = StringField(
        'Regione *',
        validators=[DataRequired(message='La regione è obbligatoria.'), Length(max=100)]
    )
    provincia = StringField(
        'Provincia (sigla)',
        validators=[Optional(), Length(max=5)]
    )
    indirizzo = StringField(
        'Indirizzo / Luogo',
        validators=[Optional(), Length(max=255)]
    )
    data_inizio = DateField(
        'Data inizio *',
        validators=[DataRequired(message='La data di inizio è obbligatoria.')]
    )
    data_fine = DateField(
        'Data fine *',
        validators=[DataRequired(message='La data di fine è obbligatoria.')]
    )
    orario = StringField(
        'Orario (es. 10:00 - 19:00)',
        validators=[Optional(), Length(max=100)]
    )
    sito_web = StringField(
        'Sito web',
        validators=[Optional(), URL(message='Inserisci un URL valido (es. https://...).'), Length(max=500)]
    )
    telefono = StringField(
        'Telefono',
        validators=[Optional(), Length(max=30)]
    )
    email_contatto = StringField(
        'Email contatto',
        validators=[Optional(), Email(message='Email non valida.'), Length(max=255)]
    )
    ingresso_gratuito = BooleanField('Ingresso gratuito', default=True)
    prezzo_ingresso = DecimalField(
        'Prezzo ingresso (€)',
        validators=[Optional(), NumberRange(min=0, max=999.99)],
        places=2
    )
    numero_espositori = IntegerField(
        'Numero espositori',
        validators=[Optional(), NumberRange(min=1, max=10000)]
    )
    categorie = MultiCheckboxField(
        'Categorie',
        coerce=int,
        validators=[Optional()]
    )
    pubblicato = BooleanField('Pubblica subito')

    def validate_data_fine(self, field):
        if self.data_inizio.data and field.data:
            if field.data < self.data_inizio.data:
                raise ValidationError('La data di fine non può essere precedente alla data di inizio.')

    def validate_prezzo_ingresso(self, field):
        if not self.ingresso_gratuito.data and field.data is None:
            raise ValidationError('Inserisci il prezzo oppure seleziona "Ingresso gratuito".')
