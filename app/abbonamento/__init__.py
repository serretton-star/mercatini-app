from flask import Blueprint
abbonamento = Blueprint('abbonamento', __name__)
from app.abbonamento import routes  # noqa: F401, E402
