import os
from flask import Flask, redirect, url_for
from app.config import config
from app.extensions import db, migrate, login_manager, bcrypt, socketio, mail


def create_app(config_name='development'):
    app = Flask(__name__)
    app.config.from_object(config.get(config_name, config['default']))

    # ── Initialise extensions ──────────────────────────────────────────────────
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    bcrypt.init_app(app)
    socketio.init_app(
        app,
        cors_allowed_origins='*',
        async_mode='threading',
        logger=False,
        engineio_logger=False,
    )
    mail.init_app(app)

    # ── Register blueprints ────────────────────────────────────────────────────
    from app.blueprints.auth import auth_bp
    from app.blueprints.tasks import tasks_bp
    from app.blueprints.chat import chat_bp
    from app.blueprints.dashboard import dashboard_bp
    from app.blueprints.admin import admin_bp
    from app.blueprints.notifications import notifications_bp
    from app.blueprints.api import api_bp
    from app.blueprints.reports import reports_bp
    from app.blueprints.recurring import recurring_bp
    from app.blueprints.client_portal import portal_bp
    from app.blueprints.goals import goals_bp
    from app.blueprints.sprints import sprints_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(tasks_bp)
    app.register_blueprint(chat_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(notifications_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(recurring_bp)
    app.register_blueprint(portal_bp)
    app.register_blueprint(goals_bp)
    app.register_blueprint(sprints_bp)

    # ── Register SocketIO handlers ─────────────────────────────────────────────
    from app.blueprints.chat.socket_handlers import register_chat_handlers
    from app.blueprints.notifications.socket_handlers import register_notification_handlers
    register_chat_handlers(socketio)
    register_notification_handlers(socketio)

    # ── Root redirect ──────────────────────────────────────────────────────────
    @app.route('/')
    def index():
        return redirect(url_for('dashboard.index'))

    # ── Error handlers ─────────────────────────────────────────────────────────
    @app.errorhandler(403)
    def forbidden(e):
        from flask import render_template
        return render_template('errors/403.html'), 403

    @app.errorhandler(404)
    def not_found(e):
        from flask import render_template
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def server_error(e):
        from flask import render_template
        return render_template('errors/500.html'), 500

    # ── Jinja2 globals and filters ─────────────────────────────────────────────
    from app.utils.helpers import format_datetime, truncate
    app.jinja_env.filters['datefmt'] = format_datetime
    app.jinja_env.filters['truncate_text'] = truncate

    @app.context_processor
    def inject_globals():
        from flask import session
        from flask_login import current_user
        from flask_wtf.csrf import generate_csrf
        from app.models.notification import Notification
        from app.models.task import STATUS_LABELS
        unread_count = 0
        active_timer = None
        if current_user.is_authenticated:
            unread_count = Notification.query.filter_by(
                user_id=current_user.id, is_read=False
            ).count()
            active_timer = session.get('active_timer')
        return {
            'unread_notif_count': unread_count,
            'ROLE_ADMIN': 'admin',
            'ROLE_TEAM_LEADER': 'team_leader',
            'ROLE_TEAM_MEMBER': 'team_member',
            'csrf_token': generate_csrf,
            'STATUS_LABELS': STATUS_LABELS,
            'active_timer': active_timer,
        }

    # ── CLI commands ───────────────────────────────────────────────────────────
    register_cli_commands(app)

    @app.cli.command('generate-recurring')
    def cli_generate_recurring():
        """Generate tasks from active recurring definitions that are due."""
        from app.blueprints.recurring.routes import generate_recurring_tasks
        with app.app_context():
            count = generate_recurring_tasks()
            print(f'{count} task(s) generated.')

    return app


def register_cli_commands(app):
    @app.cli.command('seed')
    def seed():
        """Seed the database with initial data."""
        from app.models.user import User, Team
        from app.models.task import TaskCategory
        from app.models.client import Client

        # Admin user
        admin_email = os.environ.get('ADMIN_EMAIL', 'admin@taskmanager.local')
        admin_password = os.environ.get('ADMIN_PASSWORD', 'Admin@123')
        admin_name = os.environ.get('ADMIN_NAME', 'System Administrator')

        if not User.query.filter_by(email=admin_email).first():
            admin = User(name=admin_name, email=admin_email, role='admin', is_active=True)
            admin.set_password(admin_password)
            db.session.add(admin)
            print(f'Created admin: {admin_email} / {admin_password}')
        else:
            print(f'Admin already exists: {admin_email}')

        # Default task categories
        default_categories = [
            ('GST', 'Goods and Services Tax filing and returns', '#28a745'),
            ('TDS', 'Tax Deducted at Source', '#17a2b8'),
            ('ITR', 'Income Tax Return filing', '#007bff'),
            ('Audit', 'Audit and assurance work', '#6f42c1'),
            ('Payroll', 'Payroll processing and compliance', '#fd7e14'),
            ('MIS', 'Management Information System reports', '#20c997'),
            ('ROC', 'Registrar of Companies filings', '#e83e8c'),
            ('Other', 'General and miscellaneous tasks', '#6c757d'),
        ]
        for name, desc, color in default_categories:
            if not TaskCategory.query.filter_by(name=name).first():
                cat = TaskCategory(name=name, description=desc, color_code=color)
                db.session.add(cat)
                print(f'Created category: {name}')

        # Sample team
        if not Team.query.filter_by(name='Tax Team Alpha').first():
            team = Team(name='Tax Team Alpha', description='Primary tax filing team')
            db.session.add(team)
            print('Created team: Tax Team Alpha')

        # Sample client
        if not Client.query.filter_by(code='DEMO001').first():
            client = Client(
                name='Demo Client Ltd',
                code='DEMO001',
                contact_person='John Demo',
                email='john@democlient.com',
                is_active=True,
            )
            db.session.add(client)
            print('Created sample client: Demo Client Ltd')

        db.session.commit()
        print('Seed complete.')
