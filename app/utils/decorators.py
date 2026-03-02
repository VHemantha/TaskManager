from functools import wraps
from flask import abort
from flask_login import login_required, current_user


def role_required(*roles):
    """Restrict a route to users with any of the specified roles."""
    def decorator(f):
        @wraps(f)
        @login_required
        def decorated_function(*args, **kwargs):
            if not current_user.is_active:
                abort(403)
            if current_user.role not in roles:
                abort(403)
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def active_required(f):
    """Ensure the logged-in user account is active."""
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not current_user.is_active:
            abort(403)
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    """Shortcut: admin-only route."""
    return role_required('admin')(f)


def leader_required(f):
    """Shortcut: admin or team_leader only."""
    return role_required('admin', 'team_leader')(f)
