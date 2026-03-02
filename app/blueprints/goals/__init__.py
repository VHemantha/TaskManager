from flask import Blueprint

goals_bp = Blueprint('goals', __name__, url_prefix='/goals')

from app.blueprints.goals import routes  # noqa: F401, E402
