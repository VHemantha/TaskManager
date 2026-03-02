from datetime import datetime, timezone
from app.extensions import db

DEP_BLOCKS     = 'blocks'      # this task blocks another task
DEP_BLOCKED_BY = 'blocked_by'  # this task is blocked by another task

DEP_LABELS = {
    DEP_BLOCKS:     'Blocks',
    DEP_BLOCKED_BY: 'Blocked by',
}
DEP_COLORS = {
    DEP_BLOCKS:     'danger',
    DEP_BLOCKED_BY: 'warning',
}


class TaskDependency(db.Model):
    __tablename__ = 'task_dependencies'

    id            = db.Column(db.Integer, primary_key=True)
    task_id       = db.Column(db.Integer, db.ForeignKey('tasks.id'), nullable=False, index=True)
    depends_on_id = db.Column(db.Integer, db.ForeignKey('tasks.id'), nullable=False)
    dep_type      = db.Column(db.String(20), nullable=False, default=DEP_BLOCKED_BY)
    created_at    = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    task       = db.relationship('Task', foreign_keys=[task_id],
                                 backref=db.backref('dependencies', lazy='dynamic'))
    depends_on = db.relationship('Task', foreign_keys=[depends_on_id],
                                 backref=db.backref('blocking', lazy='dynamic'))

    __table_args__ = (
        db.UniqueConstraint('task_id', 'depends_on_id', name='uq_task_dependency'),
    )

    @property
    def dep_label(self):
        return DEP_LABELS.get(self.dep_type, self.dep_type)

    @property
    def dep_color(self):
        return DEP_COLORS.get(self.dep_type, 'secondary')

    def __repr__(self):
        return f'<TaskDependency task={self.task_id} {self.dep_type} {self.depends_on_id}>'
