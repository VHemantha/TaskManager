from datetime import datetime, timezone
from app.extensions import db

# Action type constants
ACTIVITY_CREATED        = 'created'
ACTIVITY_STATUS_CHANGED = 'status_changed'
ACTIVITY_COMMENT        = 'comment'
ACTIVITY_ATTACHMENT     = 'attachment'
ACTIVITY_ASSIGNEE       = 'assignee_changed'
ACTIVITY_PRIORITY       = 'priority_changed'
ACTIVITY_DUE_DATE       = 'due_date_changed'
ACTIVITY_TITLE          = 'title_changed'
ACTIVITY_CHECKLIST      = 'checklist'
ACTIVITY_SUBTASK        = 'subtask'
ACTIVITY_TIME_LOG       = 'time_log'
ACTIVITY_DEPENDENCY     = 'dependency'

ACTIVITY_ICONS = {
    ACTIVITY_CREATED:        'plus-circle',
    ACTIVITY_STATUS_CHANGED: 'arrow-left-right',
    ACTIVITY_COMMENT:        'chat-left-text',
    ACTIVITY_ATTACHMENT:     'paperclip',
    ACTIVITY_ASSIGNEE:       'person-plus',
    ACTIVITY_PRIORITY:       'exclamation-circle',
    ACTIVITY_DUE_DATE:       'calendar',
    ACTIVITY_TITLE:          'pencil',
    ACTIVITY_CHECKLIST:      'check2-square',
    ACTIVITY_SUBTASK:        'diagram-2',
    ACTIVITY_TIME_LOG:       'stopwatch',
    ACTIVITY_DEPENDENCY:     'link-45deg',
}


class TaskActivity(db.Model):
    __tablename__ = 'task_activities'

    id          = db.Column(db.Integer, primary_key=True)
    task_id     = db.Column(db.Integer, db.ForeignKey('tasks.id'), nullable=False, index=True)
    user_id     = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    action_type = db.Column(db.String(40), nullable=False)
    detail      = db.Column(db.Text, nullable=True)
    created_at  = db.Column(db.DateTime,
                            default=lambda: datetime.now(timezone.utc),
                            index=True)

    task  = db.relationship('Task',
                            backref=db.backref('activities', lazy='dynamic',
                                               order_by='TaskActivity.created_at.desc()'))
    actor = db.relationship('User', lazy='select')

    @property
    def icon(self):
        return ACTIVITY_ICONS.get(self.action_type, 'circle')

    def __repr__(self):
        return f'<TaskActivity task={self.task_id} {self.action_type}>'
