from datetime import datetime, timezone, timedelta
from flask import render_template, redirect, url_for
from flask_login import login_required, current_user
from app.blueprints.dashboard import dashboard_bp
from app.extensions import db
from app.models.user import User, ROLE_ADMIN, ROLE_TEAM_LEADER, ROLE_TEAM_MEMBER
from app.models.task import (Task, TaskAssignment, STATUS_LABELS,
                              STATUS_ASSIGNED, STATUS_IN_PROGRESS, STATUS_COMPLETED,
                              STATUS_ESCALATED, PRIORITY_URGENT, PRIORITY_HIGH)
from app.models.notification import Notification


def _utcnow():
    """Naive UTC datetime — consistent with what SQLite returns for DateTime columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


@dashboard_bp.route('/')
@login_required
def index():
    """Route to role-appropriate dashboard."""
    if current_user.role in (ROLE_ADMIN,):
        return redirect(url_for('dashboard.admin'))
    if current_user.role == ROLE_TEAM_LEADER:
        return redirect(url_for('dashboard.leader'))
    return redirect(url_for('dashboard.member'))


@dashboard_bp.route('/leader')
@login_required
def leader():
    if current_user.role not in (ROLE_ADMIN, ROLE_TEAM_LEADER):
        return redirect(url_for('dashboard.member'))

    now = _utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    deadline_window = now + timedelta(hours=48)

    total_tasks = Task.query.count()
    in_progress = Task.query.filter_by(status=STATUS_IN_PROGRESS).count()
    completed_today = Task.query.filter(
        Task.status == STATUS_COMPLETED,
        Task.completed_at >= today_start
    ).count()
    overdue = Task.query.filter(
        Task.due_date < now,
        Task.status.notin_([STATUS_COMPLETED, 'cancelled'])
    ).count()
    escalated = Task.query.filter_by(status=STATUS_ESCALATED).count()

    # Team workload: tasks per member
    members = User.query.filter_by(is_active=True, role=ROLE_TEAM_MEMBER).all()
    workload = []
    for m in members:
        count = TaskAssignment.query.filter_by(user_id=m.id).join(Task).filter(
            Task.status.notin_([STATUS_COMPLETED, 'cancelled'])
        ).count()
        workload.append({'name': m.get_display_name(), 'count': count})

    # Upcoming deadlines
    upcoming = Task.query.filter(
        Task.due_date.between(now, deadline_window),
        Task.status.notin_([STATUS_COMPLETED, 'cancelled'])
    ).order_by(Task.due_date).limit(10).all()

    # Recent activity (last 10 status changes)
    from app.models.task import TaskStatusHistory
    recent = TaskStatusHistory.query.order_by(TaskStatusHistory.changed_at.desc()).limit(10).all()

    # Urgent/High tasks
    urgent_tasks = Task.query.filter(
        Task.priority.in_([PRIORITY_URGENT, PRIORITY_HIGH]),
        Task.status.notin_([STATUS_COMPLETED, 'cancelled'])
    ).order_by(Task.due_date).limit(8).all()

    from app.models.sprint import Sprint, SPRINT_ACTIVE
    from app.models.goal import Goal
    active_sprint = Sprint.query.filter_by(status=SPRINT_ACTIVE).first()
    goals_summary = Goal.query.filter_by(is_archived=False).order_by(Goal.target_date).limit(5).all()

    return render_template(
        'dashboard/leader.html', title='Team Dashboard',
        total_tasks=total_tasks, in_progress=in_progress,
        completed_today=completed_today, overdue=overdue, escalated=escalated,
        workload=workload, upcoming=upcoming, recent=recent,
        urgent_tasks=urgent_tasks, STATUS_LABELS=STATUS_LABELS,
        active_sprint=active_sprint, goals_summary=goals_summary,
    )


@dashboard_bp.route('/member')
@login_required
def member():
    assigned_task_ids = db.session.query(TaskAssignment.task_id).filter_by(
        user_id=current_user.id
    ).subquery()

    my_tasks = Task.query.filter(
        Task.id.in_(assigned_task_ids),
        Task.status.notin_([STATUS_COMPLETED, 'cancelled'])
    ).order_by(Task.due_date).all()

    now = _utcnow()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    deadline_window = now + timedelta(hours=48)

    completed_today = Task.query.filter(
        Task.id.in_(assigned_task_ids),
        Task.status == STATUS_COMPLETED,
        Task.completed_at >= today_start,
    ).count()

    upcoming = [t for t in my_tasks if t.due_date and t.due_date <= deadline_window]

    recent_notifications = Notification.query.filter_by(
        user_id=current_user.id, is_read=False
    ).order_by(Notification.created_at.desc()).limit(5).all()

    return render_template(
        'dashboard/member.html', title='My Dashboard',
        my_tasks=my_tasks, completed_today=completed_today,
        upcoming=upcoming, recent_notifications=recent_notifications,
        STATUS_LABELS=STATUS_LABELS,
    )


@dashboard_bp.route('/admin')
@login_required
def admin():
    if current_user.role != ROLE_ADMIN:
        return redirect(url_for('dashboard.leader'))

    now = _utcnow()
    total_tasks = Task.query.count()
    total_users = User.query.filter_by(is_active=True).count()
    overdue = Task.query.filter(
        Task.due_date < now,
        Task.status.notin_([STATUS_COMPLETED, 'cancelled'])
    ).count()
    escalated = Task.query.filter_by(status=STATUS_ESCALATED).all()

    # Per-team workload
    from app.models.user import Team
    teams = Team.query.all()
    team_stats = []
    for team in teams:
        member_ids = [u.id for u in team.members.all()]
        active = 0
        if member_ids:
            task_ids = db.session.query(TaskAssignment.task_id).filter(
                TaskAssignment.user_id.in_(member_ids)
            ).subquery()
            active = Task.query.filter(
                Task.id.in_(task_ids),
                Task.status.notin_([STATUS_COMPLETED, 'cancelled'])
            ).count()
        team_stats.append({'name': team.name, 'active_tasks': active, 'members': len(member_ids)})

    return render_template(
        'dashboard/admin.html', title='Operations Dashboard',
        total_tasks=total_tasks, total_users=total_users,
        overdue=overdue, escalated=escalated, team_stats=team_stats,
    )
