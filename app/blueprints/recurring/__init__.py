from flask import Blueprint

recurring_bp = Blueprint('recurring', __name__, url_prefix='/recurring')

from app.blueprints.recurring import routes  # noqa
