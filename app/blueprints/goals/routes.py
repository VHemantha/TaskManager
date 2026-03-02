from flask import render_template, redirect, url_for, flash, request, jsonify, abort
from flask_login import login_required, current_user
from app.blueprints.goals import goals_bp
from app.blueprints.goals.forms import GoalForm
from app.extensions import db
from app.models.goal import Goal, GoalTask, GOAL_STATUS_LABELS
from app.models.user import User, Team, ROLE_ADMIN, ROLE_TEAM_LEADER
from app.utils.decorators import role_required


def _populate_goal_form(form):
    users = User.query.filter_by(is_active=True).order_by(User.name).all()
    form.owner_id.choices = [(u.id, u.name) for u in users]
    teams = Team.query.order_by(Team.name).all()
    form.team_id.choices = [(0, '— No team —')] + [(t.id, t.name) for t in teams]


@goals_bp.route('/')
@login_required
def index():
    goals = Goal.query.filter_by(is_archived=False).order_by(Goal.target_date).all()
    return render_template('goals/index.html', title='Goals', goals=goals)


@goals_bp.route('/new', methods=['GET', 'POST'])
@login_required
@role_required(ROLE_ADMIN, ROLE_TEAM_LEADER)
def new_goal():
    form = GoalForm()
    _populate_goal_form(form)
    if form.validate_on_submit():
        goal = Goal(
            name=form.name.data.strip(),
            description=form.description.data,
            owner_id=form.owner_id.data,
            team_id=form.team_id.data if form.team_id.data != 0 else None,
            target_date=form.target_date.data,
            status=form.status.data,
        )
        db.session.add(goal)
        db.session.commit()
        flash(f'Goal "{goal.name}" created.', 'success')
        return redirect(url_for('goals.detail', goal_id=goal.id))
    return render_template('goals/form.html', form=form, title='New Goal', goal=None)


@goals_bp.route('/<int:goal_id>')
@login_required
def detail(goal_id):
    goal = Goal.query.get_or_404(goal_id)
    linked_tasks = [gt.task for gt in goal.goal_tasks.all() if gt.task]
    return render_template('goals/detail.html', title=goal.name, goal=goal,
                           linked_tasks=linked_tasks)


@goals_bp.route('/<int:goal_id>/edit', methods=['GET', 'POST'])
@login_required
@role_required(ROLE_ADMIN, ROLE_TEAM_LEADER)
def edit_goal(goal_id):
    goal = Goal.query.get_or_404(goal_id)
    form = GoalForm(obj=goal)
    _populate_goal_form(form)
    if form.validate_on_submit():
        goal.name = form.name.data.strip()
        goal.description = form.description.data
        goal.owner_id = form.owner_id.data
        goal.team_id = form.team_id.data if form.team_id.data != 0 else None
        goal.target_date = form.target_date.data
        goal.status = form.status.data
        db.session.commit()
        flash('Goal updated.', 'success')
        return redirect(url_for('goals.detail', goal_id=goal.id))
    form.team_id.data = goal.team_id or 0
    return render_template('goals/form.html', form=form, title=f'Edit Goal', goal=goal)


@goals_bp.route('/<int:goal_id>/link-task', methods=['POST'])
@login_required
@role_required(ROLE_ADMIN, ROLE_TEAM_LEADER)
def link_task(goal_id):
    goal = Goal.query.get_or_404(goal_id)
    data = request.get_json() or {}
    task_id = data.get('task_id')
    if not task_id:
        return jsonify({'error': 'task_id required'}), 400
    existing = GoalTask.query.filter_by(goal_id=goal_id, task_id=task_id).first()
    if existing:
        return jsonify({'error': 'Already linked'}), 409
    gt = GoalTask(goal_id=goal_id, task_id=task_id)
    db.session.add(gt)
    db.session.commit()
    goal.recalculate_progress()
    db.session.commit()
    return jsonify({'success': True, 'progress': goal.progress})


@goals_bp.route('/<int:goal_id>/unlink-task/<int:task_id>', methods=['POST'])
@login_required
@role_required(ROLE_ADMIN, ROLE_TEAM_LEADER)
def unlink_task(goal_id, task_id):
    gt = GoalTask.query.filter_by(goal_id=goal_id, task_id=task_id).first_or_404()
    db.session.delete(gt)
    goal = Goal.query.get_or_404(goal_id)
    db.session.commit()
    goal.recalculate_progress()
    db.session.commit()
    flash('Task unlinked from goal.', 'success')
    return redirect(url_for('goals.detail', goal_id=goal_id))


@goals_bp.route('/<int:goal_id>/archive', methods=['POST'])
@login_required
@role_required(ROLE_ADMIN, ROLE_TEAM_LEADER)
def archive_goal(goal_id):
    goal = Goal.query.get_or_404(goal_id)
    goal.is_archived = not goal.is_archived
    db.session.commit()
    state = 'archived' if goal.is_archived else 'unarchived'
    flash(f'Goal {state}.', 'success')
    return redirect(url_for('goals.index'))


@goals_bp.route('/<int:goal_id>/recalculate', methods=['POST'])
@login_required
@role_required(ROLE_ADMIN, ROLE_TEAM_LEADER)
def recalculate(goal_id):
    goal = Goal.query.get_or_404(goal_id)
    goal.recalculate_progress()
    db.session.commit()
    flash(f'Progress recalculated: {goal.progress}%.', 'success')
    return redirect(url_for('goals.detail', goal_id=goal_id))
