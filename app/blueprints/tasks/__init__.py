from flask import Blueprint

tasks_bp = Blueprint('tasks', __name__, url_prefix='/tasks')

from app.blueprints.tasks import routes  # noqa: F401, E402
