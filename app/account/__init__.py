from flask import Blueprint

account = Blueprint('account', __name__)

from app.account import routes  # noqa: F401, E402
