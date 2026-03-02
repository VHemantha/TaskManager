from datetime import datetime, timezone
from app.extensions import db

# Priority constants
PRIORITY_URGENT = 'urgent'
PRIORITY_HIGH = 'high'
PRIORITY_MEDIUM = 'medium'
PRIORITY_LOW = 'low'

PRIORITY_ORDER = {PRIORITY_URGENT: 1, PRIORITY_HIGH: 2, PRIORITY_MEDIUM: 3, PRIORITY_LOW: 4}
PRIORITY_LABELS = {
    PRIORITY_URGENT: 'Urgent',
    PRIORITY_HIGH: 'High',
    PRIORITY_MEDIUM: 'Medium',
    PRIORITY_LOW: 'Low',
}
PRIORITY_COLORS = {
    PRIORITY_URGENT: 'danger',
    PRIORITY_HIGH: 'warning',
    PRIORITY_MEDIUM: 'info',
    PRIORITY_LOW: 'secondary',
}

# Status constants
STATUS_UNASSIGNED = 'unassigned'
STATUS_ASSIGNED = 'assigned'
STATUS_IN_PROGRESS = 'in_progress'
STATUS_ON_HOLD = 'on_hold'
STATUS_UNDER_REVIEW = 'under_review'
STATUS_COMPLETED = 'completed'
STATUS_ESCALATED = 'escalated'
STATUS_CANCELLED = 'cancelled'

STATUS_LABELS = {
    STATUS_UNASSIGNED: 'Unassigned',
    STATUS_ASSIGNED: 'Assigned',
    STATUS_IN_PROGRESS: 'In Progress',
    STATUS_ON_HOLD: 'On Hold',
    STATUS_UNDER_REVIEW: 'Under Review',
    STATUS_COMPLETED: 'Completed',
    STATUS_ESCALATED: 'Escalated',
    STATUS_CANCELLED: 'Cancelled',
}

STATUS_COLORS = {
    STATUS_UNASSIGNED: 'secondary',
    STATUS_ASSIGNED: 'primary',
    STATUS_IN_PROGRESS: 'info',
    STATUS_ON_HOLD: 'warning',
    STATUS_UNDER_REVIEW: 'purple',
    STATUS_COMPLETED: 'success',
    STATUS_ESCALATED: 'danger',
    STATUS_CANCELLED: 'dark',
}

# Valid status transitions per role
MEMBER_TRANSITIONS = {
    STATUS_ASSIGNED:      [STATUS_IN_PROGRESS],
    STATUS_IN_PROGRESS:   [STATUS_ON_HOLD, STATUS_UNDER_REVIEW, STATUS_COMPLETED],
    STATUS_ON_HOLD:       [STATUS_IN_PROGRESS],
    STATUS_UNDER_REVIEW:  [STATUS_COMPLETED, STATUS_IN_PROGRESS],
}

LEADER_TRANSITIONS = {
    STATUS_UNASSIGNED: [STATUS_ASSIGNED, STATUS_CANCELLED],
    STATUS_ASSIGNED: [STATUS_IN_PROGRESS, STATUS_CANCELLED, STATUS_ESCALATED],
    STATUS_IN_PROGRESS: [STATUS_ON_HOLD, STATUS_UNDER_REVIEW, STATUS_ESCALATED, STATUS_CANCELLED],
    STATUS_ON_HOLD: [STATUS_IN_PROGRESS, STATUS_ESCALATED, STATUS_CANCELLED],
    STATUS_UNDER_REVIEW: [STATUS_COMPLETED, STATUS_IN_PROGRESS, STATUS_ESCALATED],
    STATUS_ESCALATED: [STATUS_IN_PROGRESS, STATUS_CANCELLED],
}

KANBAN_COLUMNS = [
    STATUS_UNASSIGNED,
    STATUS_ASSIGNED,
    STATUS_IN_PROGRESS,
    STATUS_ON_HOLD,
    STATUS_UNDER_REVIEW,
    STATUS_COMPLETED,
    STATUS_ESCALATED,
]


class TaskCategory(db.Model):
    __tablename__ = 'task_categories'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    description = db.Column(db.String(200), nullable=True)
    color_code = db.Column(db.String(7), default='#6c757d')

    tasks = db.relationship('Task', back_populates='category', lazy='dynamic')

    def __repr__(self):
        return f'<TaskCategory {self.name}>'


class Task(db.Model):
    __tablename__ = 'tasks'

    id = db.Column(db.Integer, primary_key=True)
    task_no = db.Column(db.String(20), unique=True, nullable=False, index=True)
    title = db.Column(db.String(300), nullable=False)
    description = db.Column(db.Text, nullable=True)

    category_id = db.Column(db.Integer, db.ForeignKey('task_categories.id'), nullable=True)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id'), nullable=True)
    assigned_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    priority = db.Column(db.String(10), nullable=False, default=PRIORITY_MEDIUM)
    status = db.Column(db.String(20), nullable=False, default=STATUS_UNASSIGNED, index=True)

    due_date = db.Column(db.DateTime, nullable=True)
    estimated_hours = db.Column(db.Float, nullable=True)
    actual_hours = db.Column(db.Float, default=0.0)

    tags = db.Column(db.String(500), nullable=True)  # comma-separated

    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))
    completed_at = db.Column(db.DateTime, nullable=True)

    # Subtask self-reference
    parent_id = db.Column(db.Integer, db.ForeignKey('tasks.id', use_alter=True, name='fk_task_parent'), nullable=True)
    subtasks  = db.relationship('Task',
                                backref=db.backref('parent', remote_side='Task.id'),
                                lazy='dynamic',
                                foreign_keys='Task.parent_id')

    # Relationships
    category = db.relationship('TaskCategory', back_populates='tasks', lazy='select')
    client = db.relationship('Client', back_populates='tasks', lazy='select')
    creator = db.relationship('User', foreign_keys=[assigned_by], backref='created_tasks', lazy='select')
    assignments = db.relationship('TaskAssignment', back_populates='task', cascade='all, delete-orphan', lazy='dynamic')
    status_history = db.relationship('TaskStatusHistory', back_populates='task',
                                     cascade='all, delete-orphan', order_by='TaskStatusHistory.changed_at', lazy='dynamic')
    comments = db.relationship('TaskComment', back_populates='task',
                               cascade='all, delete-orphan', order_by='TaskComment.created_at', lazy='dynamic')
    attachments = db.relationship('TaskAttachment', back_populates='task',
                                  cascade='all, delete-orphan', lazy='dynamic')
    time_logs = db.relationship('TimeLog', back_populates='task',
                                cascade='all, delete-orphan', lazy='dynamic')

    @property
    def subtask_count(self):
        return self.subtasks.count()

    @property
    def subtask_done_count(self):
        return self.subtasks.filter_by(status=STATUS_COMPLETED).count()

    @property
    def is_subtask(self):
        return self.parent_id is not None

    @property
    def checklist_done_count(self):
        return sum(1 for i in self.checklist_items if i.is_done)

    @property
    def checklist_total_count(self):
        return self.checklist_items.count() if hasattr(self.checklist_items, 'count') else len(list(self.checklist_items))

    @property
    def assignees(self):
        return [a.user for a in self.assignments.all() if a.user]

    @property
    def primary_assignee(self):
        primary = self.assignments.filter_by(is_primary=True).first()
        if primary:
            return primary.user
        first = self.assignments.first()
        return first.user if first else None

    @property
    def is_overdue(self):
        if self.due_date and self.status not in (STATUS_COMPLETED, STATUS_CANCELLED):
            return datetime.now(timezone.utc) > self.due_date.replace(tzinfo=timezone.utc) if self.due_date.tzinfo is None else datetime.now(timezone.utc) > self.due_date
        return False

    @property
    def priority_color(self):
        return PRIORITY_COLORS.get(self.priority, 'secondary')

    @property
    def status_color(self):
        return STATUS_COLORS.get(self.status, 'secondary')

    @property
    def priority_label(self):
        return PRIORITY_LABELS.get(self.priority, self.priority.title())

    @property
    def status_label(self):
        return STATUS_LABELS.get(self.status, self.status.replace('_', ' ').title())

    @property
    def tags_list(self):
        if self.tags:
            return [t.strip() for t in self.tags.split(',') if t.strip()]
        return []

    def get_allowed_transitions(self, user_role):
        from app.models.user import ROLE_ADMIN, ROLE_TEAM_LEADER
        if user_role in (ROLE_ADMIN, ROLE_TEAM_LEADER):
            return LEADER_TRANSITIONS.get(self.status, [])
        return MEMBER_TRANSITIONS.get(self.status, [])

    def __repr__(self):
        return f'<Task {self.task_no}: {self.title[:40]}>'


class TaskAssignment(db.Model):
    __tablename__ = 'task_assignments'

    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('tasks.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    assigned_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    is_primary = db.Column(db.Boolean, default=False)

    task = db.relationship('Task', back_populates='assignments')
    user = db.relationship('User', backref='task_assignments', lazy='select')

    __table_args__ = (db.UniqueConstraint('task_id', 'user_id', name='uq_task_user'),)


class TaskStatusHistory(db.Model):
    __tablename__ = 'task_status_history'

    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('tasks.id'), nullable=False)
    changed_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    old_status = db.Column(db.String(20), nullable=True)
    new_status = db.Column(db.String(20), nullable=False)
    changed_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    notes = db.Column(db.Text, nullable=True)

    task = db.relationship('Task', back_populates='status_history')
    changed_by_user = db.relationship('User', backref='status_changes', lazy='select')
