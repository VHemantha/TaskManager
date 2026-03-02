from flask import render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from app.blueprints.sprints import sprints_bp
from app.blueprints.sprints.forms import SprintForm
from app.extensions import db
from app.models.sprint import Sprint, SprintTask, SPRINT_ACTIVE, SPRINT_COMPLETED, SPRINT_PLANNING
from app.models.task import Task, STATUS_LABELS, KANBAN_COLUMNS
from app.models.user import User, Team, ROLE_ADMIN, ROLE_TEAM_LEADER
from app.utils.decorators import role_required


def _populate_sprint_form(form):
    teams = Team.query.order_by(Team.name).all()
    form.team_id.choices = [(0, '— No team —')] + [(t.id, t.name) for t in teams]


@sprints_bp.route('/')
@login_required
def index():
    sprints = Sprint.query.order_by(Sprint.created_at.desc()).all()
    return render_template('sprints/index.html', title='Sprints', sprints=sprints)


@sprints_bp.route('/new', methods=['GET', 'POST'])
@login_required
@role_required(ROLE_ADMIN, ROLE_TEAM_LEADER)
def new_sprint():
    form = SprintForm()
    _populate_sprint_form(form)
    if form.validate_on_submit():
        sprint = Sprint(
            name=form.name.data.strip(),
            goal=form.goal.data,
            team_id=form.team_id.data if form.team_id.data != 0 else None,
            start_date=form.start_date.data,
            end_date=form.end_date.data,
            status=form.status.data,
            created_by=current_user.id,
        )
        db.session.add(sprint)
        db.session.commit()
        flash(f'Sprint "{sprint.name}" created.', 'success')
        return redirect(url_for('sprints.board', sprint_id=sprint.id))
    return render_template('sprints/form.html', form=form, title='New Sprint', sprint=None)


@sprints_bp.route('/<int:sprint_id>')
@login_required
def board(sprint_id):
    sprint = Sprint.query.get_or_404(sprint_id)
    sprint_task_ids = {st.task_id for st in sprint.sprint_tasks.all()}
    tasks_in_sprint = Task.query.filter(Task.id.in_(sprint_task_ids)).all() if sprint_task_ids else []

    # Group by status for kanban-style board
    tasks_by_status = {}
    for status in KANBAN_COLUMNS:
        tasks_by_status[status] = [t for t in tasks_in_sprint if t.status == status]

    # Velocity: planned vs completed story points
    planned_pts = sum(st.story_points or 1 for st in sprint.sprint_tasks.all())
    completed_pts = sum(
        st.story_points or 1 for st in sprint.sprint_tasks.all()
        if st.task and st.task.status == 'completed'
    )

    return render_template('sprints/board.html', title=sprint.name,
                           sprint=sprint, tasks_by_status=tasks_by_status,
                           STATUS_LABELS=STATUS_LABELS, KANBAN_COLUMNS=KANBAN_COLUMNS,
                           planned_pts=planned_pts, completed_pts=completed_pts)


@sprints_bp.route('/<int:sprint_id>/edit', methods=['GET', 'POST'])
@login_required
@role_required(ROLE_ADMIN, ROLE_TEAM_LEADER)
def edit_sprint(sprint_id):
    sprint = Sprint.query.get_or_404(sprint_id)
    form = SprintForm(obj=sprint)
    _populate_sprint_form(form)
    if form.validate_on_submit():
        sprint.name = form.name.data.strip()
        sprint.goal = form.goal.data
        sprint.team_id = form.team_id.data if form.team_id.data != 0 else None
        sprint.start_date = form.start_date.data
        sprint.end_date = form.end_date.data
        sprint.status = form.status.data
        db.session.commit()
        flash('Sprint updated.', 'success')
        return redirect(url_for('sprints.board', sprint_id=sprint.id))
    form.team_id.data = sprint.team_id or 0
    return render_template('sprints/form.html', form=form, title='Edit Sprint', sprint=sprint)


@sprints_bp.route('/<int:sprint_id>/add-task', methods=['POST'])
@login_required
@role_required(ROLE_ADMIN, ROLE_TEAM_LEADER)
def add_task(sprint_id):
    sprint = Sprint.query.get_or_404(sprint_id)
    data = request.get_json() or {}
    task_id = data.get('task_id')
    story_points = int(data.get('story_points', 1))
    if not task_id:
        return jsonify({'error': 'task_id required'}), 400
    task = Task.query.get_or_404(task_id)
    existing = SprintTask.query.filter_by(sprint_id=sprint_id, task_id=task_id).first()
    if existing:
        return jsonify({'error': 'Task already in sprint'}), 409
    st = SprintTask(sprint_id=sprint_id, task_id=task_id, story_points=story_points)
    db.session.add(st)
    db.session.commit()
    return jsonify({'success': True, 'task_no': task.task_no, 'title': task.title})


@sprints_bp.route('/<int:sprint_id>/remove-task/<int:task_id>', methods=['POST'])
@login_required
@role_required(ROLE_ADMIN, ROLE_TEAM_LEADER)
def remove_task(sprint_id, task_id):
    st = SprintTask.query.filter_by(sprint_id=sprint_id, task_id=task_id).first_or_404()
    db.session.delete(st)
    db.session.commit()
    flash('Task removed from sprint.', 'success')
    return redirect(url_for('sprints.board', sprint_id=sprint_id))


@sprints_bp.route('/<int:sprint_id>/activate', methods=['POST'])
@login_required
@role_required(ROLE_ADMIN, ROLE_TEAM_LEADER)
def activate(sprint_id):
    sprint = Sprint.query.get_or_404(sprint_id)
    sprint.status = SPRINT_ACTIVE
    db.session.commit()
    flash(f'Sprint "{sprint.name}" activated.', 'success')
    return redirect(url_for('sprints.board', sprint_id=sprint_id))


@sprints_bp.route('/<int:sprint_id>/complete', methods=['POST'])
@login_required
@role_required(ROLE_ADMIN, ROLE_TEAM_LEADER)
def complete_sprint(sprint_id):
    sprint = Sprint.query.get_or_404(sprint_id)
    sprint.status = SPRINT_COMPLETED
    db.session.commit()
    flash(f'Sprint "{sprint.name}" marked as completed.', 'success')
    return redirect(url_for('sprints.board', sprint_id=sprint_id))
