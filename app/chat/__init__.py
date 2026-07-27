from flask import Blueprint

chat = Blueprint('chat', __name__)

from app.chat import routes  # noqa: F401, E402
