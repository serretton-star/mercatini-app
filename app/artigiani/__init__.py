from flask import Blueprint
artigiani = Blueprint('artigiani', __name__)
from app.artigiani import routes  # noqa
