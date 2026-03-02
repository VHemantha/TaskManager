import csv
from io import StringIO
from datetime import datetime, timezone, timedelta

from flask import render_template, request, Response
from flask_login import login_required, current_user

from app.blueprints.reports import reports_bp
from app.extensions import db
from app.models.task import Task, TaskAssignment, TaskCategory, STATUS_LABELS, PRIORITY_LABELS
from app.models.user import User, ROLE_ADMIN, ROLE_TEAM_LEADER
from app.models.client import Client
from app.models.time_log import TimeLog
from app.utils.decorators import role_required


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _parse_date(s):
    if not s:
        return None
    try:
        return datetime.strptime(s, '%Y-%m-%d')
    except ValueError:
        return None


def _default_range():
    now = _utcnow()
    return now - timedelta(days=30), now


@reports_bp.route('/')
@login_required
@role_required(ROLE_ADMIN, ROLE_TEAM_LEADER)
def index():
    now = _utcnow()
    total = Task.query.count()
    completed = Task.query.filter_by(status='completed').count()
    in_progress = Task.query.filter_by(status='in_progress').count()
    overdue = Task.query.filter(
        Task.due_date < now,
        Task.status.notin_(['completed', 'cancelled'])
    ).count()
    total_hours = db.session.query(db.func.sum(TimeLog.hours)).scalar() or 0
    members = User.query.filter_by(is_active=True, role='team_member').count()
    return render_template(
        'reports/index.html', title='Reports & Analytics',
        total=total, completed=completed, in_progress=in_progress,
        overdue=overdue, total_hours=round(total_hours, 1), members=members,
    )


@reports_bp.route('/tasks')
@login_required
@role_required(ROLE_ADMIN, ROLE_TEAM_LEADER)
def task_report():
    df, dt = _default_range()
    date_from = _parse_date(request.args.get('date_from')) or df
    date_to = _parse_date(request.args.get('date_to')) or dt
    client_id = request.args.get('client_id', 0, type=int)
    category_id = request.args.get('category_id', 0, type=int)

    query = Task.query.filter(Task.created_at >= date_from, Task.created_at <= date_to)
    if client_id:
        query = query.filter(Task.client_id == client_id)
    if category_id:
        query = query.filter(Task.category_id == category_id)

    tasks = query.order_by(Task.created_at.desc()).all()

    by_status, by_priority, by_category = {}, {}, {}
    for t in tasks:
        by_status[t.status] = by_status.get(t.status, 0) + 1
        by_priority[t.priority] = by_priority.get(t.priority, 0) + 1
        cat = t.category.name if t.category else 'Uncategorized'
        by_category[cat] = by_category.get(cat, 0) + 1

    if request.args.get('export') == 'csv':
        return _export_tasks_csv(tasks)

    clients = Client.query.filter_by(is_active=True).order_by(Client.name).all()
    categories = TaskCategory.query.order_by(TaskCategory.name).all()
    return render_template(
        'reports/tasks.html', title='Task Report',
        tasks=tasks, by_status=by_status, by_priority=by_priority, by_category=by_category,
        STATUS_LABELS=STATUS_LABELS, PRIORITY_LABELS=PRIORITY_LABELS,
        date_from=date_from, date_to=date_to,
        clients=clients, categories=categories,
        client_id=client_id, category_id=category_id,
    )


@reports_bp.route('/time')
@login_required
@role_required(ROLE_ADMIN, ROLE_TEAM_LEADER)
def time_report():
    df, dt = _default_range()
    date_from = _parse_date(request.args.get('date_from')) or df
    date_to = _parse_date(request.args.get('date_to')) or dt
    user_id = request.args.get('user_id', 0, type=int)

    query = TimeLog.query.filter(TimeLog.created_at >= date_from, TimeLog.created_at <= date_to)
    if user_id:
        query = query.filter(TimeLog.user_id == user_id)

    logs = query.order_by(TimeLog.created_at.desc()).all()

    by_user, by_category = {}, {}
    for log in logs:
        uname = log.user.get_display_name() if log.user else 'Unknown'
        by_user[uname] = round(by_user.get(uname, 0) + (log.calculated_hours or 0), 2)
        cat = log.task.category.name if log.task and log.task.category else 'Uncategorized'
        by_category[cat] = round(by_category.get(cat, 0) + (log.calculated_hours or 0), 2)

    total_hours = round(sum(log.calculated_hours or 0 for log in logs), 2)

    if request.args.get('export') == 'csv':
        return _export_time_csv(logs)

    members = User.query.filter_by(is_active=True).order_by(User.name).all()
    return render_template(
        'reports/time.html', title='Time Tracking Report',
        logs=logs, by_user=by_user, by_category=by_category,
        total_hours=total_hours, date_from=date_from, date_to=date_to,
        members=members, user_id=user_id,
    )


@reports_bp.route('/team')
@login_required
@role_required(ROLE_ADMIN, ROLE_TEAM_LEADER)
def team_report():
    df, dt = _default_range()
    date_from = _parse_date(request.args.get('date_from')) or df
    date_to = _parse_date(request.args.get('date_to')) or dt

    members = User.query.filter_by(is_active=True, role='team_member').order_by(User.name).all()
    now = _utcnow()
    stats = []
    for m in members:
        assigned_ids = db.session.query(TaskAssignment.task_id).filter_by(user_id=m.id).subquery()
        total = Task.query.filter(
            Task.id.in_(assigned_ids), Task.created_at >= date_from, Task.created_at <= date_to
        ).count()
        completed = Task.query.filter(
            Task.id.in_(assigned_ids), Task.status == 'completed',
            Task.created_at >= date_from, Task.created_at <= date_to
        ).count()
        overdue = Task.query.filter(
            Task.id.in_(assigned_ids), Task.due_date < now,
            Task.status.notin_(['completed', 'cancelled'])
        ).count()
        hours = db.session.query(db.func.sum(TimeLog.hours)).filter(
            TimeLog.user_id == m.id,
            TimeLog.created_at >= date_from, TimeLog.created_at <= date_to
        ).scalar() or 0
        stats.append({
            'user': m,
            'total': total,
            'completed': completed,
            'overdue': overdue,
            'hours': round(hours, 1),
            'rate': round(completed / total * 100) if total else 0,
        })
    stats.sort(key=lambda x: x['completed'], reverse=True)

    if request.args.get('export') == 'csv':
        return _export_team_csv(stats)

    return render_template(
        'reports/team.html', title='Team Productivity',
        stats=stats, date_from=date_from, date_to=date_to,
    )


# ── CSV helpers ────────────────────────────────────────────────────────────────

def _export_tasks_csv(tasks):
    si = StringIO()
    w = csv.writer(si)
    w.writerow(['Task No', 'Title', 'Status', 'Priority', 'Category', 'Client',
                'Assignees', 'Due Date', 'Est Hours', 'Actual Hours', 'Created'])
    for t in tasks:
        w.writerow([
            t.task_no, t.title, t.status, t.priority,
            t.category.name if t.category else '',
            t.client.name if t.client else '',
            ', '.join(u.name for u in t.assignees),
            t.due_date.strftime('%Y-%m-%d') if t.due_date else '',
            t.estimated_hours or '', t.actual_hours or '',
            t.created_at.strftime('%Y-%m-%d') if t.created_at else '',
        ])
    return Response(si.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition': 'attachment;filename=tasks_report.csv'})


def _export_time_csv(logs):
    si = StringIO()
    w = csv.writer(si)
    w.writerow(['Date', 'User', 'Task No', 'Task Title', 'Category', 'Hours', 'Description'])
    for log in logs:
        w.writerow([
            log.created_at.strftime('%Y-%m-%d') if log.created_at else '',
            log.user.get_display_name() if log.user else '',
            log.task.task_no if log.task else '',
            log.task.title if log.task else '',
            log.task.category.name if log.task and log.task.category else '',
            '%.2f' % (log.calculated_hours or 0),
            log.description or '',
        ])
    return Response(si.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition': 'attachment;filename=time_report.csv'})


def _export_team_csv(stats):
    si = StringIO()
    w = csv.writer(si)
    w.writerow(['Member', 'Role', 'Total Tasks', 'Completed', 'Overdue', 'Hours Logged', 'Completion %'])
    for s in stats:
        w.writerow([
            s['user'].name, s['user'].get_role_label(),
            s['total'], s['completed'], s['overdue'], s['hours'], s['rate'],
        ])
    return Response(si.getvalue(), mimetype='text/csv',
                    headers={'Content-Disposition': 'attachment;filename=team_report.csv'})
