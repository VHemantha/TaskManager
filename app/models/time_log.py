from datetime import datetime, timezone
from app.extensions import db


class TimeLog(db.Model):
    __tablename__ = 'time_logs'

    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('tasks.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    start_time = db.Column(db.DateTime, nullable=True)
    end_time = db.Column(db.DateTime, nullable=True)
    hours = db.Column(db.Float, nullable=True)  # manual entry or calculated
    description = db.Column(db.String(300), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    task = db.relationship('Task', back_populates='time_logs')
    user = db.relationship('User', backref='time_logs', lazy='select')

    @property
    def calculated_hours(self):
        if self.hours:
            return self.hours
        if self.start_time and self.end_time:
            delta = self.end_time - self.start_time
            return round(delta.total_seconds() / 3600, 2)
        return 0.0

    def __repr__(self):
        return f'<TimeLog task={self.task_id} user={self.user_id} hours={self.calculated_hours}>'
