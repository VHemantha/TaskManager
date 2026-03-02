import csv
from io import StringIO

from flask import render_template, request, Response
from flask_login import login_required

from app.blueprints.client_portal import portal_bp
from app.extensions import db
from app.models.client import Client
from app.models.task import Task, STATUS_LABELS, PRIORITY_LABELS
from app.models.user import ROLE_ADMIN, ROLE_TEAM_LEADER
from app.utils.decorators import role_required


def _utcnow():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).replace(tzinfo=None)


@portal_bp.route('/')
@login_required
@role_required(ROLE_ADMIN, ROLE_TEAM_LEADER)
def index():
    clients = Client.query.filter_by(is_active=True).order_by(Client.name).all()
    now = _utcnow()
    stats = []
    for c in clients:
        total = Task.query.filter_by(client_id=c.id).count()
        active = Task.query.filter(
            Task.client_id == c.id,
            Task.status.notin_(['completed', 'cancelled'])
        ).count()
        completed = Task.query.filter_by(client_id=c.id, status='completed').count()
        overdue = Task.query.filter(
            Task.client_id == c.id,
            Task.due_date < now,
            Task.status.notin_(['completed', 'cancelled'])
        ).count()
        stats.append({'client': c, 'total': total, 'active': active,
                      'completed': completed, 'overdue': overdue})

    stats.sort(key=lambda x: x['active'], reverse=True)
    return render_template('client_portal/index.html', title='Client Portal', stats=stats)


@portal_bp.route('/client/<int:client_id>')
@login_required
@role_required(ROLE_ADMIN, ROLE_TEAM_LEADER)
def client_tasks(client_id):
    client = Client.query.get_or_404(client_id)
    status_filter = request.args.get('status', '')

    query = Task.query.filter_by(client_id=client_id)
    if status_filter:
        query = query.filter(Task.status == status_filter)

    tasks = query.order_by(Task.due_date.asc().nullslast(), Task.created_at.desc()).all()

    if request.args.get('export') == 'csv':
        return _export_csv(client, tasks)

    by_status = {}
    for t in tasks:
        by_status[t.status] = by_status.get(t.status, 0) + 1

    return render_template(
        'client_portal/tasks.html', title=f'{client.name}',
        client=client, tasks=tasks, by_status=by_status,
        STATUS_LABELS=STATUS_LABELS, status_filter=status_filter,
    )


def _export_csv(client, tasks):
    si = StringIO()
    w = csv.writer(si)
    w.writerow(['Task No', 'Title', 'Status', 'Priority', 'Category',
                'Assignees', 'Due Date', 'Est Hours', 'Actual Hours', 'Created'])
    for t in tasks:
        w.writerow([
            t.task_no, t.title,
            STATUS_LABELS.get(t.status, t.status), t.priority,
            t.category.name if t.category else '',
            ', '.join(u.name for u in t.assignees),
            t.due_date.strftime('%Y-%m-%d') if t.due_date else '',
            t.estimated_hours or '', t.actual_hours or '',
            t.created_at.strftime('%Y-%m-%d') if t.created_at else '',
        ])
    return Response(si.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition':
                             f'attachment;filename={client.code}_tasks.csv'})
