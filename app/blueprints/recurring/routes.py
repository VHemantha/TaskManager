from datetime import datetime, timezone

from flask import render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user

from app.blueprints.recurring import recurring_bp
from app.blueprints.recurring.forms import RecurringTaskForm
from app.extensions import db
from app.models.recurring import RecurringTask, FREQUENCY_LABELS
from app.models.task import Task, TaskAssignment, TaskStatusHistory, TaskCategory
from app.models.user import User, ROLE_ADMIN, ROLE_TEAM_LEADER
from app.models.client import Client
from app.utils.decorators import role_required
from app.utils.helpers import generate_task_no
from app.utils.notifications import notify_task_assigned


def _populate(form):
    cats = TaskCategory.query.order_by(TaskCategory.name).all()
    form.category_id.choices = [(0, '— None —')] + [(c.id, c.name) for c in cats]
    clients = Client.query.filter_by(is_active=True).order_by(Client.name).all()
    form.client_id.choices = [(0, '— None —')] + [(c.id, c.name) for c in clients]
    members = User.query.filter_by(is_active=True).order_by(User.name).all()
    form.assignees.choices = [(u.id, f'{u.name} ({u.get_role_label()})') for u in members]


@recurring_bp.route('/')
@login_required
@role_required(ROLE_ADMIN, ROLE_TEAM_LEADER)
def index():
    tasks = RecurringTask.query.order_by(RecurringTask.is_active.desc(),
                                         RecurringTask.created_at.desc()).all()
    return render_template('recurring/index.html', title='Recurring Tasks',
                           tasks=tasks, FREQUENCY_LABELS=FREQUENCY_LABELS)


@recurring_bp.route('/new', methods=['GET', 'POST'])
@login_required
@role_required(ROLE_ADMIN, ROLE_TEAM_LEADER)
def recurring_new():
    form = RecurringTaskForm()
    _populate(form)
    if form.validate_on_submit():
        rt = RecurringTask(
            title=form.title.data.strip(),
            description=form.description.data,
            category_id=form.category_id.data if form.category_id.data else None,
            client_id=form.client_id.data if form.client_id.data else None,
            priority=form.priority.data,
            estimated_hours=form.estimated_hours.data,
            frequency=form.frequency.data,
            next_due=form.first_due_date.data,
            lead_days=form.lead_days.data if form.lead_days.data is not None else 1,
            is_active=form.is_active.data,
            created_by=current_user.id,
        )
        rt.assignee_ids = form.assignees.data
        db.session.add(rt)
        db.session.commit()
        flash(f'Recurring task "{rt.title}" created.', 'success')
        return redirect(url_for('recurring.index'))
    return render_template('recurring/form.html', form=form, title='New Recurring Task', rt=None)


@recurring_bp.route('/<int:rt_id>/edit', methods=['GET', 'POST'])
@login_required
@role_required(ROLE_ADMIN, ROLE_TEAM_LEADER)
def recurring_edit(rt_id):
    rt = RecurringTask.query.get_or_404(rt_id)
    form = RecurringTaskForm()
    _populate(form)
    if form.validate_on_submit():
        rt.title = form.title.data.strip()
        rt.description = form.description.data
        rt.category_id = form.category_id.data if form.category_id.data else None
        rt.client_id = form.client_id.data if form.client_id.data else None
        rt.priority = form.priority.data
        rt.estimated_hours = form.estimated_hours.data
        rt.frequency = form.frequency.data
        rt.next_due = form.first_due_date.data
        rt.lead_days = form.lead_days.data if form.lead_days.data is not None else 1
        rt.is_active = form.is_active.data
        rt.assignee_ids = form.assignees.data
        db.session.commit()
        flash('Recurring task updated.', 'success')
        return redirect(url_for('recurring.index'))
    # Pre-fill form
    form.title.data = rt.title
    form.description.data = rt.description
    form.category_id.data = rt.category_id or 0
    form.client_id.data = rt.client_id or 0
    form.assignees.data = rt.assignee_ids
    form.priority.data = rt.priority
    form.estimated_hours.data = rt.estimated_hours
    form.frequency.data = rt.frequency
    form.first_due_date.data = rt.next_due
    form.lead_days.data = rt.lead_days
    form.is_active.data = rt.is_active
    return render_template('recurring/form.html', form=form, title=f'Edit: {rt.title}', rt=rt)


@recurring_bp.route('/<int:rt_id>/toggle', methods=['POST'])
@login_required
@role_required(ROLE_ADMIN, ROLE_TEAM_LEADER)
def recurring_toggle(rt_id):
    rt = RecurringTask.query.get_or_404(rt_id)
    rt.is_active = not rt.is_active
    db.session.commit()
    flash(f'Recurring task {"activated" if rt.is_active else "paused"}.', 'info')
    return redirect(url_for('recurring.index'))


@recurring_bp.route('/<int:rt_id>/delete', methods=['POST'])
@login_required
@role_required(ROLE_ADMIN, ROLE_TEAM_LEADER)
def recurring_delete(rt_id):
    rt = RecurringTask.query.get_or_404(rt_id)
    db.session.delete(rt)
    db.session.commit()
    flash('Recurring task deleted.', 'success')
    return redirect(url_for('recurring.index'))


@recurring_bp.route('/generate', methods=['POST'])
@login_required
@role_required(ROLE_ADMIN, ROLE_TEAM_LEADER)
def generate_now():
    """Manually trigger generation of due recurring tasks."""
    count = generate_recurring_tasks()
    flash(f'{count} task(s) generated from recurring definitions.', 'success')
    return redirect(url_for('recurring.index'))


def generate_recurring_tasks():
    """
    Generate Task instances for active recurring definitions where:
      next_due - lead_days  ≤  today
    Returns count of tasks created.
    """
    now = datetime.utcnow()
    count = 0
    for rt in RecurringTask.query.filter_by(is_active=True).all():
        if rt.next_due is None:
            continue
        from datetime import timedelta
        trigger = rt.next_due - timedelta(days=rt.lead_days or 0)
        if trigger.replace(tzinfo=None) > now:
            continue

        task = Task(
            task_no=generate_task_no(),
            title=rt.title,
            description=rt.description,
            category_id=rt.category_id,
            client_id=rt.client_id,
            assigned_by=rt.created_by,
            priority=rt.priority,
            status='assigned' if rt.assignee_ids else 'unassigned',
            due_date=rt.next_due,
            estimated_hours=rt.estimated_hours,
            tags='recurring',
        )
        db.session.add(task)
        db.session.flush()

        for i, uid in enumerate(rt.assignee_ids):
            db.session.add(TaskAssignment(task_id=task.id, user_id=uid, is_primary=(i == 0)))

        db.session.add(TaskStatusHistory(
            task_id=task.id, changed_by=rt.created_by,
            old_status=None, new_status=task.status,
            notes=f'Auto-generated from recurring task #{rt.id}',
        ))

        rt.last_generated = now
        rt.advance_next_due()
        db.session.commit()

        if rt.assignee_ids:
            notify_task_assigned(task, rt.assignee_ids)
        count += 1

    return count
