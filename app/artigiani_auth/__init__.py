from flask import Blueprint
artigiani_auth = Blueprint('artigiani_auth', __name__)
from app.artigiani_auth import routes  # noqa
