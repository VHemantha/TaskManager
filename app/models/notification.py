from datetime import datetime, timezone
from app.extensions import db

# Notification type constants
NOTIF_TASK_ASSIGNED = 'task_assigned'
NOTIF_TASK_STATUS_CHANGED = 'task_status_changed'
NOTIF_TASK_COMMENT = 'task_comment'
NOTIF_TASK_DEADLINE = 'task_deadline'
NOTIF_TASK_OVERDUE = 'task_overdue'
NOTIF_TASK_ESCALATED = 'task_escalated'
NOTIF_TASK_COMPLETED = 'task_completed'
NOTIF_FILE_UPLOADED = 'file_uploaded'


class Notification(db.Model):
    __tablename__ = 'notifications'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    type = db.Column(db.String(50), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=True)
    task_id = db.Column(db.Integer, db.ForeignKey('tasks.id'), nullable=True)
    is_read = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    user = db.relationship('User', backref='notifications', lazy='select')
    task = db.relationship('Task', backref='notifications', lazy='select')

    def to_dict(self):
        return {
            'id': self.id,
            'type': self.type,
            'title': self.title,
            'message': self.message,
            'task_id': self.task_id,
            'is_read': self.is_read,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'time_ago': self._time_ago(),
        }

    def _time_ago(self):
        now = datetime.now(timezone.utc)
        created = self.created_at.replace(tzinfo=timezone.utc) if self.created_at.tzinfo is None else self.created_at
        diff = now - created
        seconds = int(diff.total_seconds())
        if seconds < 60:
            return 'Just now'
        if seconds < 3600:
            return f'{seconds // 60}m ago'
        if seconds < 86400:
            return f'{seconds // 3600}h ago'
        return f'{seconds // 86400}d ago'

    def __repr__(self):
        return f'<Notification user={self.user_id} type={self.type}>'
