from datetime import datetime, timezone
from app.extensions import db

GOAL_ON_TRACK  = 'on_track'
GOAL_AT_RISK   = 'at_risk'
GOAL_OFF_TRACK = 'off_track'
GOAL_ACHIEVED  = 'achieved'

GOAL_STATUS_LABELS = {
    GOAL_ON_TRACK:  'On Track',
    GOAL_AT_RISK:   'At Risk',
    GOAL_OFF_TRACK: 'Off Track',
    GOAL_ACHIEVED:  'Achieved',
}
GOAL_STATUS_COLORS = {
    GOAL_ON_TRACK:  'success',
    GOAL_AT_RISK:   'warning',
    GOAL_OFF_TRACK: 'danger',
    GOAL_ACHIEVED:  'primary',
}


class Goal(db.Model):
    __tablename__ = 'goals'

    id          = db.Column(db.Integer, primary_key=True)
    name        = db.Column(db.String(300), nullable=False)
    description = db.Column(db.Text, nullable=True)
    owner_id    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    team_id     = db.Column(db.Integer, db.ForeignKey('teams.id'), nullable=True)
    target_date = db.Column(db.DateTime, nullable=True)
    progress    = db.Column(db.Integer, default=0)   # 0–100
    status      = db.Column(db.String(20), nullable=False, default=GOAL_ON_TRACK)
    is_archived = db.Column(db.Boolean, default=False, nullable=False)
    created_at  = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    owner      = db.relationship('User', foreign_keys=[owner_id], lazy='select')
    team       = db.relationship('Team', lazy='select')
    goal_tasks = db.relationship('GoalTask', back_populates='goal',
                                 cascade='all, delete-orphan', lazy='dynamic')

    @property
    def status_label(self):
        return GOAL_STATUS_LABELS.get(self.status, self.status)

    @property
    def status_color(self):
        return GOAL_STATUS_COLORS.get(self.status, 'secondary')

    @property
    def linked_task_count(self):
        return self.goal_tasks.count()

    def recalculate_progress(self):
        tasks = [gt.task for gt in self.goal_tasks.all() if gt.task]
        if not tasks:
            self.progress = 0
            return
        done = sum(1 for t in tasks if t.status == 'completed')
        self.progress = round(done / len(tasks) * 100)

    def __repr__(self):
        return f'<Goal {self.name[:40]}>'


class GoalTask(db.Model):
    __tablename__ = 'goal_tasks'

    id       = db.Column(db.Integer, primary_key=True)
    goal_id  = db.Column(db.Integer, db.ForeignKey('goals.id'), nullable=False, index=True)
    task_id  = db.Column(db.Integer, db.ForeignKey('tasks.id'), nullable=False)
    added_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    goal = db.relationship('Goal', back_populates='goal_tasks')
    task = db.relationship('Task', backref=db.backref('goal_links', lazy='dynamic'))

    __table_args__ = (
        db.UniqueConstraint('goal_id', 'task_id', name='uq_goal_task'),
    )

    def __repr__(self):
        return f'<GoalTask goal={self.goal_id} task={self.task_id}>'
