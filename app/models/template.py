import json
from datetime import datetime, timezone
from app.extensions import db


class TaskTemplate(db.Model):
    __tablename__ = 'task_templates'

    id            = db.Column(db.Integer, primary_key=True)
    name          = db.Column(db.String(200), nullable=False)
    description   = db.Column(db.Text, nullable=True)
    template_data = db.Column(db.Text, nullable=False)  # JSON blob
    created_by    = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at    = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    creator = db.relationship('User', lazy='select')

    @property
    def data(self):
        return json.loads(self.template_data)

    @data.setter
    def data(self, value):
        self.template_data = json.dumps(value)

    def __repr__(self):
        return f'<TaskTemplate {self.name}>'
