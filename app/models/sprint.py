from datetime import datetime, timezone
from app.extensions import db

SPRINT_PLANNING  = 'planning'
SPRINT_ACTIVE    = 'active'
SPRINT_COMPLETED = 'completed'

SPRINT_LABELS = {
    SPRINT_PLANNING:  'Planning',
    SPRINT_ACTIVE:    'Active',
    SPRINT_COMPLETED: 'Completed',
}
SPRINT_COLORS = {
    SPRINT_PLANNING:  'primary',
    SPRINT_ACTIVE:    'success',
    SPRINT_COMPLETED: 'secondary',
}


class Sprint(db.Model):
    __tablename__ = 'sprints'

    id         = db.Column(db.Integer, primary_key=True)
    name       = db.Column(db.String(200), nullable=False)
    goal       = db.Column(db.Text, nullable=True)
    team_id    = db.Column(db.Integer, db.ForeignKey('teams.id'), nullable=True)
    start_date = db.Column(db.DateTime, nullable=True)
    end_date   = db.Column(db.DateTime, nullable=True)
    status     = db.Column(db.String(20), nullable=False, default=SPRINT_PLANNING)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    team         = db.relationship('Team', lazy='select')
    creator      = db.relationship('User', foreign_keys=[created_by], lazy='select')
    sprint_tasks = db.relationship('SprintTask', back_populates='sprint',
                                   cascade='all, delete-orphan', lazy='dynamic')

    @property
    def status_label(self):
        return SPRINT_LABELS.get(self.status, self.status)

    @property
    def status_color(self):
        return SPRINT_COLORS.get(self.status, 'secondary')

    @property
    def task_count(self):
        return self.sprint_tasks.count()

    @property
    def completed_count(self):
        return sum(1 for st in self.sprint_tasks.all() if st.task and st.task.status == 'completed')

    @property
    def progress_pct(self):
        total = self.task_count
        return round(self.completed_count / total * 100) if total else 0

    @property
    def tasks(self):
        return [st.task for st in self.sprint_tasks.all() if st.task]

    def __repr__(self):
        return f'<Sprint {self.name}>'


class SprintTask(db.Model):
    __tablename__ = 'sprint_tasks'

    id           = db.Column(db.Integer, primary_key=True)
    sprint_id    = db.Column(db.Integer, db.ForeignKey('sprints.id'), nullable=False, index=True)
    task_id      = db.Column(db.Integer, db.ForeignKey('tasks.id'), nullable=False)
    story_points = db.Column(db.Integer, default=1)
    added_at     = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    sprint = db.relationship('Sprint', back_populates='sprint_tasks')
    task   = db.relationship('Task', backref=db.backref('sprint_links', lazy='dynamic'))

    __table_args__ = (
        db.UniqueConstraint('sprint_id', 'task_id', name='uq_sprint_task'),
    )

    def __repr__(self):
        return f'<SprintTask sprint={self.sprint_id} task={self.task_id}>'
