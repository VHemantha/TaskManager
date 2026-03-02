import os
from datetime import datetime, timezone
from flask import render_template, redirect, url_for, flash, request, abort, \
    send_from_directory, current_app, jsonify
from flask_login import login_required, current_user
from app.blueprints.tasks import tasks_bp
from app.blueprints.tasks.forms import TaskForm, StatusUpdateForm, CommentForm, \
    AttachmentForm, TimeLogForm, TaskFilterForm
from app.utils.decorators import role_required, active_required
from app.utils.helpers import generate_task_no, save_attachment
from app.utils.notifications import notify_task_assigned, notify_status_change, \
    notify_new_comment, notify_file_uploaded
from app.extensions import db, socketio
from app.models.user import User, ROLE_ADMIN, ROLE_TEAM_LEADER, ROLE_TEAM_MEMBER
from app.models.client import Client
from app.models.task import (Task, TaskAssignment, TaskCategory, TaskStatusHistory,
                              STATUS_LABELS, PRIORITY_LABELS, KANBAN_COLUMNS, STATUS_COMPLETED)
from app.models.chat import TaskComment, TaskAttachment
from app.models.time_log import TimeLog
from app.models.checklist import ChecklistItem
from app.models.dependency import TaskDependency, DEP_BLOCKED_BY


def _populate_task_form(form):
    cats = TaskCategory.query.order_by(TaskCategory.name).all()
    form.category_id.choices = [(0, '— None —')] + [(c.id, c.name) for c in cats]
    clients = Client.query.filter_by(is_active=True).order_by(Client.name).all()
    form.client_id.choices = [(0, '— None —')] + [(c.id, c.name) for c in clients]
    members = User.query.filter_by(is_active=True).order_by(User.name).all()
    form.assignees.choices = [(u.id, f'{u.name} ({u.get_role_label()})') for u in members]


@tasks_bp.route('/')
@login_required
def list_tasks():
    filter_form = TaskFilterForm(request.args)
    statuses = [('', 'All Statuses')] + [(k, v) for k, v in STATUS_LABELS.items()]
    priorities = [('', 'All Priorities')] + [(k, v) for k, v in PRIORITY_LABELS.items()]
    filter_form.status.choices = statuses
    filter_form.priority.choices = priorities

    members = User.query.filter_by(is_active=True).order_by(User.name).all()
    filter_form.assignee_id.choices = [(0, 'All Members')] + [(u.id, u.name) for u in members]
    clients = Client.query.filter_by(is_active=True).order_by(Client.name).all()
    filter_form.client_id.choices = [(0, 'All Clients')] + [(c.id, c.name) for c in clients]

    query = Task.query

    # Restrict team members to their own tasks
    if current_user.role == 'team_member':
        assigned_task_ids = db.session.query(TaskAssignment.task_id).filter_by(user_id=current_user.id).subquery()
        query = query.filter(Task.id.in_(assigned_task_ids))

    if filter_form.status.data:
        query = query.filter(Task.status == filter_form.status.data)
    if filter_form.priority.data:
        query = query.filter(Task.priority == filter_form.priority.data)
    if filter_form.assignee_id.data:
        assigned_ids = db.session.query(TaskAssignment.task_id).filter_by(user_id=filter_form.assignee_id.data).subquery()
        query = query.filter(Task.id.in_(assigned_ids))
    if filter_form.client_id.data:
        query = query.filter(Task.client_id == filter_form.client_id.data)
    if filter_form.search.data:
        q = f'%{filter_form.search.data}%'
        query = query.filter(db.or_(Task.title.ilike(q), Task.task_no.ilike(q)))

    page = request.args.get('page', 1, type=int)
    tasks = query.order_by(Task.created_at.desc()).paginate(page=page, per_page=20, error_out=False)

    return render_template('tasks/list.html', title='All Tasks', tasks=tasks, filter_form=filter_form)


@tasks_bp.route('/kanban')
@login_required
@role_required(ROLE_ADMIN, ROLE_TEAM_LEADER)
def kanban():
    tasks_by_status = {}
    for status in KANBAN_COLUMNS:
        tasks_by_status[status] = Task.query.filter_by(status=status).order_by(Task.due_date).all()
    return render_template('tasks/kanban.html', title='Kanban Board',
                           tasks_by_status=tasks_by_status,
                           kanban_columns=KANBAN_COLUMNS,
                           STATUS_LABELS=STATUS_LABELS)


@tasks_bp.route('/new', methods=['GET', 'POST'])
@login_required
@role_required(ROLE_ADMIN, ROLE_TEAM_LEADER)
def task_new():
    form = TaskForm()
    _populate_task_form(form)
    if form.validate_on_submit():
        task = Task(
            task_no=generate_task_no(),
            title=form.title.data.strip(),
            description=form.description.data,
            category_id=form.category_id.data if form.category_id.data != 0 else None,
            client_id=form.client_id.data if form.client_id.data != 0 else None,
            assigned_by=current_user.id,
            priority=form.priority.data,
            status='assigned' if form.assignees.data else 'unassigned',
            due_date=form.due_date.data,
            estimated_hours=form.estimated_hours.data,
            tags=form.tags.data,
        )
        db.session.add(task)
        db.session.flush()

        assignee_ids = []
        for i, uid in enumerate(form.assignees.data):
            assn = TaskAssignment(task_id=task.id, user_id=uid, is_primary=(i == 0))
            db.session.add(assn)
            assignee_ids.append(uid)

        history = TaskStatusHistory(
            task_id=task.id, changed_by=current_user.id,
            old_status=None, new_status=task.status
        )
        db.session.add(history)
        db.session.commit()

        if assignee_ids:
            notify_task_assigned(task, assignee_ids)

        flash(f'Task {task.task_no} created.', 'success')
        return redirect(url_for('tasks.task_detail', task_id=task.id))
    return render_template('tasks/form.html', form=form, title='New Task', task=None)


@tasks_bp.route('/<int:task_id>')
@login_required
def task_detail(task_id):
    task = Task.query.get_or_404(task_id)
    _check_task_access(task)
    comment_form = CommentForm()
    attachment_form = AttachmentForm()
    timelog_form = TimeLogForm()
    status_form = StatusUpdateForm()
    allowed_transitions = task.get_allowed_transitions(current_user.role)
    time_logs = TimeLog.query.filter_by(task_id=task_id).order_by(TimeLog.created_at.desc()).all()
    return render_template(
        'tasks/detail.html', task=task, title=task.task_no,
        comment_form=comment_form, attachment_form=attachment_form,
        timelog_form=timelog_form, status_form=status_form,
        allowed_transitions=allowed_transitions, STATUS_LABELS=STATUS_LABELS,
        time_logs=time_logs,
    )


@tasks_bp.route('/<int:task_id>/edit', methods=['GET', 'POST'])
@login_required
@role_required(ROLE_ADMIN, ROLE_TEAM_LEADER)
def task_edit(task_id):
    task = Task.query.get_or_404(task_id)
    form = TaskForm(obj=task)
    _populate_task_form(form)
    if form.validate_on_submit():
        task.title = form.title.data.strip()
        task.description = form.description.data
        task.category_id = form.category_id.data if form.category_id.data != 0 else None
        task.client_id = form.client_id.data if form.client_id.data != 0 else None
        task.priority = form.priority.data
        task.due_date = form.due_date.data
        task.estimated_hours = form.estimated_hours.data
        task.tags = form.tags.data

        # Update assignments
        TaskAssignment.query.filter_by(task_id=task.id).delete()
        new_assignee_ids = []
        for i, uid in enumerate(form.assignees.data):
            assn = TaskAssignment(task_id=task.id, user_id=uid, is_primary=(i == 0))
            db.session.add(assn)
            new_assignee_ids.append(uid)
        if new_assignee_ids and task.status == 'unassigned':
            task.status = 'assigned'

        db.session.commit()
        notify_task_assigned(task, new_assignee_ids)
        flash(f'Task {task.task_no} updated.', 'success')
        return redirect(url_for('tasks.task_detail', task_id=task.id))

    # Pre-populate assignees
    form.assignees.data = [a.user_id for a in task.assignments.all()]
    form.category_id.data = task.category_id or 0
    form.client_id.data = task.client_id or 0
    return render_template('tasks/form.html', form=form, title=f'Edit {task.task_no}', task=task)


@tasks_bp.route('/<int:task_id>/status', methods=['POST'])
@login_required
def task_status_update(task_id):
    task = Task.query.get_or_404(task_id)
    _check_task_access(task)
    form = StatusUpdateForm()
    if form.validate_on_submit():
        new_status = form.new_status.data
        allowed = task.get_allowed_transitions(current_user.role)
        if new_status not in allowed:
            abort(403)

        # Team members must log time before completing
        if new_status == STATUS_COMPLETED and current_user.role == ROLE_TEAM_MEMBER:
            logged = TimeLog.query.filter_by(task_id=task_id, user_id=current_user.id).count()
            if logged == 0:
                flash('Please log your hours before marking this task as complete.', 'warning')
                return redirect(url_for('tasks.task_detail', task_id=task_id))

        old_status = task.status
        task.status = new_status
        if new_status == STATUS_COMPLETED:
            task.completed_at = datetime.now(timezone.utc)

        history = TaskStatusHistory(
            task_id=task.id, changed_by=current_user.id,
            old_status=old_status, new_status=new_status,
            notes=form.notes.data,
        )
        db.session.add(history)
        db.session.commit()

        # Notify leader / creator
        leader_ids = list({task.assigned_by})
        notify_status_change(task, current_user.id, leader_ids)

        # Real-time push to kanban viewers
        socketio.emit('task_updated', {
            'task_id': task.id,
            'task_no': task.task_no,
            'old_status': old_status,
            'new_status': new_status,
            'status_label': task.status_label,
        }, namespace='/dashboard')

        flash(f'Status updated to {task.status_label}.', 'success')
    return redirect(url_for('tasks.task_detail', task_id=task_id))


@tasks_bp.route('/<int:task_id>/comment', methods=['POST'])
@login_required
def task_comment(task_id):
    task = Task.query.get_or_404(task_id)
    _check_task_access(task)
    form = CommentForm()
    if form.validate_on_submit():
        comment = TaskComment(
            task_id=task_id,
            user_id=current_user.id,
            message=form.message.data.strip(),
        )
        db.session.add(comment)
        db.session.commit()

        participant_ids = [a.user_id for a in task.assignments.all()] + [task.assigned_by]
        notify_new_comment(task, current_user.id, list(set(participant_ids)))
        flash('Comment posted.', 'success')
    return redirect(url_for('tasks.task_detail', task_id=task_id))


@tasks_bp.route('/<int:task_id>/upload', methods=['POST'])
@login_required
def task_upload(task_id):
    task = Task.query.get_or_404(task_id)
    _check_task_access(task)
    file = request.files.get('file')
    if not file or file.filename == '':
        flash('No file selected.', 'warning')
        return redirect(url_for('tasks.task_detail', task_id=task_id))
    try:
        orig_name, rel_path, filesize, mimetype = save_attachment(file, task_id)
        attachment = TaskAttachment(
            task_id=task_id,
            uploaded_by=current_user.id,
            filename=orig_name,
            filepath=rel_path,
            filesize=filesize,
            mimetype=mimetype,
        )
        db.session.add(attachment)
        db.session.commit()

        participant_ids = [a.user_id for a in task.assignments.all()] + [task.assigned_by]
        notify_file_uploaded(task, current_user.id, list(set(participant_ids)))
        flash(f'File "{orig_name}" uploaded.', 'success')
    except ValueError as e:
        flash(str(e), 'danger')
    return redirect(url_for('tasks.task_detail', task_id=task_id))


@tasks_bp.route('/<int:task_id>/attachment/<int:attachment_id>')
@login_required
def task_download(task_id, attachment_id):
    task = Task.query.get_or_404(task_id)
    _check_task_access(task)
    attachment = TaskAttachment.query.filter_by(id=attachment_id, task_id=task_id).first_or_404()
    upload_folder = current_app.config['UPLOAD_FOLDER']
    directory = os.path.join(upload_folder, str(task_id))
    filename = os.path.basename(attachment.filepath)
    return send_from_directory(directory, filename, as_attachment=True,
                               download_name=attachment.filename)


@tasks_bp.route('/<int:task_id>/timelog', methods=['POST'])
@login_required
def task_timelog(task_id):
    task = Task.query.get_or_404(task_id)
    _check_task_access(task)
    form = TimeLogForm()
    if form.validate_on_submit():
        log = TimeLog(
            task_id=task_id,
            user_id=current_user.id,
            hours=form.hours.data,
            description=form.description.data,
        )
        db.session.add(log)
        # Update actual hours on task
        task.actual_hours = (task.actual_hours or 0) + form.hours.data
        db.session.commit()
        flash(f'{form.hours.data}h logged.', 'success')
    return redirect(url_for('tasks.task_detail', task_id=task_id))


@tasks_bp.route('/kanban/move', methods=['POST'])
@login_required
@role_required(ROLE_ADMIN, ROLE_TEAM_LEADER)
def kanban_move():
    """AJAX endpoint: drag-and-drop status update from kanban."""
    data = request.get_json()
    task_id = data.get('task_id')
    new_status = data.get('new_status')
    task = Task.query.get_or_404(task_id)
    allowed = task.get_allowed_transitions(current_user.role)
    if new_status not in allowed:
        return jsonify({'error': 'Transition not allowed'}), 403
    if new_status == STATUS_COMPLETED and current_user.role == ROLE_TEAM_MEMBER:
        logged = TimeLog.query.filter_by(task_id=task_id, user_id=current_user.id).count()
        if logged == 0:
            return jsonify({'error': 'Please log your hours before completing this task'}), 400
    old_status = task.status
    task.status = new_status
    if new_status == STATUS_COMPLETED:
        task.completed_at = datetime.now(timezone.utc)
    history = TaskStatusHistory(
        task_id=task.id, changed_by=current_user.id,
        old_status=old_status, new_status=new_status,
    )
    db.session.add(history)
    db.session.commit()
    socketio.emit('task_updated', {
        'task_id': task.id, 'task_no': task.task_no,
        'old_status': old_status, 'new_status': new_status,
    }, namespace='/dashboard')
    return jsonify({'success': True, 'task_no': task.task_no, 'new_status': new_status})


def _check_task_access(task):
    """Abort 403 if current user has no access to this task."""
    if current_user.role in (ROLE_ADMIN, ROLE_TEAM_LEADER):
        return
    assigned_ids = [a.user_id for a in task.assignments.all()]
    if current_user.id not in assigned_ids:
        abort(403)


# ── Subtasks ──────────────────────────────────────────────────────────────────

@tasks_bp.route('/<int:task_id>/subtask', methods=['POST'])
@login_required
@role_required(ROLE_ADMIN, ROLE_TEAM_LEADER)
def task_add_subtask(task_id):
    task = Task.query.get_or_404(task_id)
    data = request.get_json() or {}
    title = (data.get('title') or '').strip()
    if not title:
        return jsonify({'error': 'title required'}), 400
    sub = Task(
        task_no=generate_task_no(),
        title=title,
        description=data.get('description', ''),
        assigned_by=current_user.id,
        priority=task.priority,
        status='unassigned',
        parent_id=task.id,
    )
    db.session.add(sub)
    db.session.commit()
    return jsonify({
        'success': True, 'task_id': sub.id, 'task_no': sub.task_no,
        'title': sub.title, 'status': sub.status,
        'status_label': sub.status_label, 'status_color': sub.status_color,
        'url': url_for('tasks.task_detail', task_id=sub.id),
    })


@tasks_bp.route('/<int:task_id>/subtasks')
@login_required
def task_subtasks(task_id):
    task = Task.query.get_or_404(task_id)
    return jsonify([{
        'id': s.id, 'task_no': s.task_no, 'title': s.title,
        'status': s.status, 'status_label': s.status_label,
        'status_color': s.status_color,
        'url': url_for('tasks.task_detail', task_id=s.id),
    } for s in task.subtasks.all()])


# ── Checklists ────────────────────────────────────────────────────────────────

@tasks_bp.route('/<int:task_id>/checklist', methods=['POST'])
@login_required
def task_checklist_add(task_id):
    task = Task.query.get_or_404(task_id)
    _check_task_access(task)
    data = request.get_json() or {}
    content = (data.get('content') or '').strip()
    if not content:
        return jsonify({'error': 'content required'}), 400
    max_pos = db.session.query(db.func.max(ChecklistItem.position)).filter_by(task_id=task_id).scalar() or 0
    item = ChecklistItem(task_id=task_id, content=content, position=max_pos + 1)
    db.session.add(item)
    db.session.commit()
    return jsonify(item.to_dict())


@tasks_bp.route('/<int:task_id>/checklist/<int:item_id>/toggle', methods=['POST'])
@login_required
def task_checklist_toggle(task_id, item_id):
    task = Task.query.get_or_404(task_id)
    _check_task_access(task)
    item = ChecklistItem.query.filter_by(id=item_id, task_id=task_id).first_or_404()
    item.is_done = not item.is_done
    db.session.commit()
    total = ChecklistItem.query.filter_by(task_id=task_id).count()
    done = ChecklistItem.query.filter_by(task_id=task_id, is_done=True).count()
    pct = round(done / total * 100) if total else 0
    return jsonify({'id': item.id, 'is_done': item.is_done, 'progress_pct': pct, 'done': done, 'total': total})


@tasks_bp.route('/<int:task_id>/checklist/<int:item_id>/delete', methods=['POST'])
@login_required
def task_checklist_delete(task_id, item_id):
    task = Task.query.get_or_404(task_id)
    _check_task_access(task)
    item = ChecklistItem.query.filter_by(id=item_id, task_id=task_id).first_or_404()
    db.session.delete(item)
    db.session.commit()
    total = ChecklistItem.query.filter_by(task_id=task_id).count()
    done = ChecklistItem.query.filter_by(task_id=task_id, is_done=True).count()
    pct = round(done / total * 100) if total else 0
    return jsonify({'success': True, 'progress_pct': pct, 'done': done, 'total': total})


@tasks_bp.route('/<int:task_id>/checklist/reorder', methods=['POST'])
@login_required
def task_checklist_reorder(task_id):
    task = Task.query.get_or_404(task_id)
    _check_task_access(task)
    data = request.get_json() or []
    for entry in data:
        item = ChecklistItem.query.filter_by(id=entry.get('id'), task_id=task_id).first()
        if item:
            item.position = entry.get('position', item.position)
    db.session.commit()
    return jsonify({'success': True})


# ── Dependencies ──────────────────────────────────────────────────────────────

@tasks_bp.route('/<int:task_id>/dependency', methods=['POST'])
@login_required
@role_required(ROLE_ADMIN, ROLE_TEAM_LEADER)
def add_dependency(task_id):
    task = Task.query.get_or_404(task_id)
    task_no = (request.form.get('task_no') or '').strip()
    dep_type = request.form.get('dep_type', DEP_BLOCKED_BY)
    depends_on = Task.query.filter_by(task_no=task_no).first()
    if not depends_on:
        flash(f'Task "{task_no}" not found.', 'danger')
        return redirect(url_for('tasks.task_detail', task_id=task_id))
    if depends_on.id == task_id:
        flash('A task cannot depend on itself.', 'danger')
        return redirect(url_for('tasks.task_detail', task_id=task_id))
    existing = TaskDependency.query.filter_by(task_id=task_id, depends_on_id=depends_on.id).first()
    if existing:
        flash('Dependency already exists.', 'warning')
        return redirect(url_for('tasks.task_detail', task_id=task_id))
    dep = TaskDependency(task_id=task_id, depends_on_id=depends_on.id, dep_type=dep_type)
    db.session.add(dep)
    db.session.commit()
    flash('Dependency added.', 'success')
    return redirect(url_for('tasks.task_detail', task_id=task_id))


@tasks_bp.route('/<int:task_id>/dependency/<int:dep_id>/delete', methods=['POST'])
@login_required
@role_required(ROLE_ADMIN, ROLE_TEAM_LEADER)
def delete_dependency(task_id, dep_id):
    dep = TaskDependency.query.filter_by(id=dep_id, task_id=task_id).first_or_404()
    db.session.delete(dep)
    db.session.commit()
    flash('Dependency removed.', 'success')
    return redirect(url_for('tasks.task_detail', task_id=task_id))


# ── Task Templates ────────────────────────────────────────────────────────────

@tasks_bp.route('/templates')
@login_required
@role_required(ROLE_ADMIN, ROLE_TEAM_LEADER)
def task_templates():
    from app.models.template import TaskTemplate
    templates = TaskTemplate.query.order_by(TaskTemplate.name).all()
    return render_template('tasks/templates.html', templates=templates, title='Task Templates')


@tasks_bp.route('/<int:task_id>/save-as-template', methods=['POST'])
@login_required
@role_required(ROLE_ADMIN, ROLE_TEAM_LEADER)
def save_as_template(task_id):
    from app.models.template import TaskTemplate
    task = Task.query.get_or_404(task_id)
    name = (request.form.get('template_name') or '').strip()
    if not name:
        flash('Template name is required.', 'danger')
        return redirect(url_for('tasks.task_detail', task_id=task_id))
    tpl = TaskTemplate(name=name, description=task.description, created_by=current_user.id)
    tpl.data = {
        'title': task.title, 'description': task.description,
        'priority': task.priority, 'estimated_hours': task.estimated_hours,
        'tags': task.tags,
        'checklist': [{'content': i.content, 'position': i.position}
                      for i in task.checklist_items.order_by(ChecklistItem.position).all()],
    }
    db.session.add(tpl)
    db.session.commit()
    flash(f'Template "{name}" saved.', 'success')
    return redirect(url_for('tasks.task_detail', task_id=task_id))


# ── New View Routes ───────────────────────────────────────────────────────────

@tasks_bp.route('/calendar')
@login_required
def calendar_view():
    import json
    query = Task.query
    if current_user.role == 'team_member':
        assigned_ids = db.session.query(TaskAssignment.task_id).filter_by(user_id=current_user.id).subquery()
        query = query.filter(Task.id.in_(assigned_ids))
    tasks = query.filter(Task.due_date.isnot(None)).all()
    color_map = {'urgent': '#ef4444', 'high': '#f59e0b', 'medium': '#3b82f6', 'low': '#6b7280'}
    tasks_json = json.dumps([{
        'id': t.id,
        'title': f'[{t.task_no}] {t.title}',
        'start': t.due_date.strftime('%Y-%m-%d'),
        'url': url_for('tasks.task_detail', task_id=t.id),
        'color': color_map.get(t.priority, '#6b7280'),
        'extendedProps': {'status': t.status_label, 'priority': t.priority_label},
    } for t in tasks])
    return render_template('tasks/calendar.html', title='Calendar', tasks_json=tasks_json, active_view='calendar')


@tasks_bp.route('/table')
@login_required
def table_view():
    query = Task.query
    if current_user.role == 'team_member':
        assigned_ids = db.session.query(TaskAssignment.task_id).filter_by(user_id=current_user.id).subquery()
        query = query.filter(Task.id.in_(assigned_ids))
    tasks = query.order_by(Task.created_at.desc()).all()
    from app.models.task import STATUS_LABELS as SL, PRIORITY_LABELS as PL
    return render_template('tasks/table.html', title='Table View', tasks=tasks, active_view='table',
                           STATUS_LABELS=SL, PRIORITY_LABELS=PL)


@tasks_bp.route('/workload')
@login_required
@role_required(ROLE_ADMIN, ROLE_TEAM_LEADER)
def workload_view():
    from datetime import date, timedelta
    members = User.query.filter_by(is_active=True, role=ROLE_TEAM_MEMBER).all()
    today = datetime.now(timezone.utc).date()
    days = [today + timedelta(days=i) for i in range(14)]
    workload_grid = {}
    for m in members:
        assigned_task_ids = db.session.query(TaskAssignment.task_id).filter_by(user_id=m.id).subquery()
        tasks = Task.query.filter(
            Task.id.in_(assigned_task_ids),
            Task.due_date.isnot(None),
            Task.status.notin_(['completed', 'cancelled']),
        ).all()
        grid = {}
        for day in days:
            day_str = day.strftime('%Y-%m-%d')
            grid[day_str] = [t for t in tasks if t.due_date and t.due_date.date() == day]
        workload_grid[m.id] = {'user': m, 'grid': grid}
    return render_template('tasks/workload.html', title='Workload', members=members,
                           days=days, workload_grid=workload_grid, active_view='workload')


@tasks_bp.route('/matrix')
@login_required
def matrix_view():
    query = Task.query.filter(Task.status.notin_(['completed', 'cancelled']))
    if current_user.role == 'team_member':
        assigned_ids = db.session.query(TaskAssignment.task_id).filter_by(user_id=current_user.id).subquery()
        query = query.filter(Task.id.in_(assigned_ids))
    tasks = query.all()
    urgent_important     = [t for t in tasks if t.priority in ('urgent', 'high') and t.status in ('in_progress', 'under_review', 'assigned')]
    not_urgent_important = [t for t in tasks if t.priority in ('medium', 'low') and t.status in ('in_progress', 'under_review', 'assigned')]
    urgent_not_important = [t for t in tasks if t.priority in ('urgent', 'high') and t.status in ('on_hold', 'unassigned', 'escalated')]
    eliminate            = [t for t in tasks if t.priority in ('medium', 'low') and t.status in ('on_hold', 'unassigned')]
    return render_template('tasks/matrix.html', title='Priority Matrix', active_view='matrix',
                           urgent_important=urgent_important,
                           not_urgent_important=not_urgent_important,
                           urgent_not_important=urgent_not_important,
                           eliminate=eliminate)


@tasks_bp.route('/<int:task_id>/inline-edit', methods=['PATCH'])
@login_required
@role_required(ROLE_ADMIN, ROLE_TEAM_LEADER)
def task_inline_edit(task_id):
    task = Task.query.get_or_404(task_id)
    data = request.get_json() or {}
    field = data.get('field')
    value = data.get('value')
    if field == 'title' and value:
        task.title = value.strip()
    elif field == 'priority' and value in ('urgent', 'high', 'medium', 'low'):
        task.priority = value
    elif field == 'due_date':
        if value:
            try:
                task.due_date = datetime.strptime(value, '%Y-%m-%d')
            except ValueError:
                return jsonify({'error': 'Invalid date format'}), 400
        else:
            task.due_date = None
    elif field == 'status' and value in STATUS_LABELS:
        task.status = value
    else:
        return jsonify({'error': 'Unknown or invalid field'}), 400
    db.session.commit()
    return jsonify({'success': True})
