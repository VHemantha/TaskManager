from flask import Blueprint

portal_bp = Blueprint('portal', __name__, url_prefix='/portal')

from app.blueprints.client_portal import routes  # noqa
