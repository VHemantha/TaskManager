import calendar
from datetime import datetime, timezone, timedelta
from app.extensions import db

FREQ_DAILY = 'daily'
FREQ_WEEKLY = 'weekly'
FREQ_MONTHLY = 'monthly'
FREQ_QUARTERLY = 'quarterly'
FREQ_ANNUALLY = 'annually'

FREQUENCY_LABELS = {
    FREQ_DAILY: 'Daily',
    FREQ_WEEKLY: 'Weekly',
    FREQ_MONTHLY: 'Monthly',
    FREQ_QUARTERLY: 'Quarterly',
    FREQ_ANNUALLY: 'Annually',
}


def _add_months(dt, n):
    """Add n months to a datetime, clamping day to valid range."""
    month = dt.month - 1 + n
    year = dt.year + month // 12
    month = month % 12 + 1
    day = min(dt.day, calendar.monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)


class RecurringTask(db.Model):
    __tablename__ = 'recurring_tasks'

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(300), nullable=False)
    description = db.Column(db.Text, nullable=True)
    category_id = db.Column(db.Integer, db.ForeignKey('task_categories.id'), nullable=True)
    client_id = db.Column(db.Integer, db.ForeignKey('clients.id'), nullable=True)
    _assignee_ids = db.Column('assignee_ids', db.String(500), nullable=True)
    priority = db.Column(db.String(10), default='medium')
    estimated_hours = db.Column(db.Float, nullable=True)

    frequency = db.Column(db.String(20), nullable=False, default=FREQ_MONTHLY)
    lead_days = db.Column(db.Integer, default=1)       # create task N days before due date
    next_due = db.Column(db.DateTime, nullable=True)   # next task due date
    last_generated = db.Column(db.DateTime, nullable=True)

    is_active = db.Column(db.Boolean, default=True)
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    category = db.relationship('TaskCategory', lazy='select')
    client = db.relationship('Client', lazy='select')
    creator = db.relationship('User', foreign_keys=[created_by], lazy='select')

    @property
    def assignee_ids(self):
        if not self._assignee_ids:
            return []
        return [int(x) for x in self._assignee_ids.split(',') if x.strip().isdigit()]

    @assignee_ids.setter
    def assignee_ids(self, ids):
        self._assignee_ids = ','.join(str(i) for i in ids) if ids else ''

    @property
    def frequency_label(self):
        return FREQUENCY_LABELS.get(self.frequency, self.frequency.title())

    def advance_next_due(self):
        """Shift next_due forward by one frequency interval."""
        if self.next_due is None:
            return
        nd = self.next_due
        if self.frequency == FREQ_DAILY:
            self.next_due = nd + timedelta(days=1)
        elif self.frequency == FREQ_WEEKLY:
            self.next_due = nd + timedelta(weeks=1)
        elif self.frequency == FREQ_MONTHLY:
            self.next_due = _add_months(nd, 1)
        elif self.frequency == FREQ_QUARTERLY:
            self.next_due = _add_months(nd, 3)
        elif self.frequency == FREQ_ANNUALLY:
            try:
                self.next_due = nd.replace(year=nd.year + 1)
            except ValueError:  # Feb 29 → Feb 28
                self.next_due = nd.replace(year=nd.year + 1, day=28)

    def __repr__(self):
        return f'<RecurringTask {self.frequency}: {self.title[:40]}>'
