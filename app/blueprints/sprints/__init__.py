from flask import Blueprint

sprints_bp = Blueprint('sprints', __name__, url_prefix='/sprints')

from app.blueprints.sprints import routes  # noqa: F401, E402
