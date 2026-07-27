from flask import Blueprint

mercatini = Blueprint('mercatini', __name__)

from app.mercatini import routes  # noqa: F401, E402
