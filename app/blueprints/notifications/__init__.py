from flask import Blueprint

notifications_bp = Blueprint('notifications', __name__, url_prefix='/notifications')

from app.blueprints.notifications import routes  # noqa: F401, E402
