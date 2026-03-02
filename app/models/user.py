from datetime import datetime, timezone
from flask_login import UserMixin
from app.extensions import db, login_manager

# Role constants
ROLE_ADMIN = 'admin'
ROLE_TEAM_LEADER = 'team_leader'
ROLE_TEAM_MEMBER = 'team_member'
ROLE_CLIENT_MANAGER = 'client_manager'

ALL_ROLES = [ROLE_ADMIN, ROLE_TEAM_LEADER, ROLE_TEAM_MEMBER, ROLE_CLIENT_MANAGER]
ROLE_LABELS = {
    ROLE_ADMIN: 'Admin',
    ROLE_TEAM_LEADER: 'Team Leader',
    ROLE_TEAM_MEMBER: 'Team Member',
    ROLE_CLIENT_MANAGER: 'Client Manager',
}


class Team(db.Model):
    __tablename__ = 'teams'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    description = db.Column(db.Text)
    leader_id = db.Column(db.Integer, db.ForeignKey('users.id', use_alter=True, name='fk_team_leader'), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    # Relationships
    leader = db.relationship('User', foreign_keys=[leader_id], backref='led_teams', lazy='select')
    members = db.relationship('User', foreign_keys='User.team_id', back_populates='team', lazy='dynamic')

    def __repr__(self):
        return f'<Team {self.name}>'


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(30), nullable=False, default=ROLE_TEAM_MEMBER)
    team_id = db.Column(db.Integer, db.ForeignKey('teams.id'), nullable=True)
    avatar = db.Column(db.String(255), nullable=True)
    phone = db.Column(db.String(20), nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    last_seen = db.Column(db.DateTime, nullable=True)

    # Password reset token fields
    reset_token = db.Column(db.String(100), nullable=True)
    reset_token_expires = db.Column(db.DateTime, nullable=True)

    # Notification preferences
    email_notifications = db.Column(db.Boolean, default=True)

    # Relationships
    team = db.relationship('Team', foreign_keys=[team_id], back_populates='members', lazy='select')

    def set_password(self, password):
        from app.extensions import bcrypt
        self.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')

    def check_password(self, password):
        from app.extensions import bcrypt
        return bcrypt.check_password_hash(self.password_hash, password)

    def get_display_name(self):
        return self.name or self.email.split('@')[0]

    def get_role_label(self):
        return ROLE_LABELS.get(self.role, self.role)

    def is_admin(self):
        return self.role == ROLE_ADMIN

    def is_team_leader(self):
        return self.role == ROLE_TEAM_LEADER

    def is_team_member(self):
        return self.role == ROLE_TEAM_MEMBER

    def get_avatar_url(self):
        if self.avatar:
            return f'/static/uploads/avatars/{self.avatar}'
        # Gravatar-style fallback using initials
        return None

    def get_initials(self):
        parts = self.name.split()
        if len(parts) >= 2:
            return (parts[0][0] + parts[-1][0]).upper()
        return self.name[:2].upper() if self.name else '??'

    def __repr__(self):
        return f'<User {self.email}>'


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))
