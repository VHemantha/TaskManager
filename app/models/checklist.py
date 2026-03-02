from datetime import datetime, timezone
from app.extensions import db


class ChecklistItem(db.Model):
    __tablename__ = 'checklist_items'

    id         = db.Column(db.Integer, primary_key=True)
    task_id    = db.Column(db.Integer, db.ForeignKey('tasks.id'), nullable=False, index=True)
    content    = db.Column(db.String(500), nullable=False)
    is_done    = db.Column(db.Boolean, default=False, nullable=False)
    position   = db.Column(db.Integer, default=0, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    task = db.relationship('Task', backref=db.backref('checklist_items', order_by='ChecklistItem.position', lazy='dynamic'))

    def to_dict(self):
        return {
            'id':       self.id,
            'content':  self.content,
            'is_done':  self.is_done,
            'position': self.position,
        }

    def __repr__(self):
        return f'<ChecklistItem {self.id}: {self.content[:30]}>'
