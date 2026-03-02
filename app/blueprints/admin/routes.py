from flask import render_template, redirect, url_for, flash, request, abort
from flask_login import current_user
from app.blueprints.admin import admin_bp
from app.blueprints.admin.forms import UserForm, TeamForm, ClientForm, TaskCategoryForm
from app.utils.decorators import admin_required, leader_required
from app.extensions import db
from app.models.user import User, Team, ROLE_LABELS
from app.models.client import Client
from app.models.task import TaskCategory


@admin_bp.route('/')
@admin_required
def index():
    user_count = User.query.count()
    team_count = Team.query.count()
    client_count = Client.query.count()
    return render_template('admin/index.html', title='Admin Panel',
                           user_count=user_count, team_count=team_count, client_count=client_count)


# ── Users ──────────────────────────────────────────────────────────────────────

@admin_bp.route('/users')
@admin_required
def users():
    page = request.args.get('page', 1, type=int)
    users = User.query.order_by(User.name).paginate(
        page=page, per_page=25, error_out=False
    )
    return render_template('admin/users.html', title='User Management', users=users)


@admin_bp.route('/users/new', methods=['GET', 'POST'])
@admin_required
def user_new():
    form = UserForm()
    form.team_id.choices = [(0, '— No Team —')] + [(t.id, t.name) for t in Team.query.order_by(Team.name).all()]
    if form.validate_on_submit():
        existing = User.query.filter_by(email=form.email.data.lower().strip()).first()
        if existing:
            flash('Email already registered.', 'danger')
        else:
            user = User(
                name=form.name.data.strip(),
                email=form.email.data.lower().strip(),
                role=form.role.data,
                team_id=form.team_id.data if form.team_id.data != 0 else None,
                phone=form.phone.data,
                is_active=form.is_active.data,
            )
            if form.password.data:
                user.set_password(form.password.data)
            else:
                user.set_password('ChangeMe@123')
            db.session.add(user)
            db.session.commit()
            flash(f'User {user.name} created.', 'success')
            return redirect(url_for('admin.users'))
    return render_template('admin/user_form.html', form=form, title='New User', user=None)


@admin_bp.route('/users/<int:user_id>/edit', methods=['GET', 'POST'])
@admin_required
def user_edit(user_id):
    user = User.query.get_or_404(user_id)
    form = UserForm(obj=user)
    form.team_id.choices = [(0, '— No Team —')] + [(t.id, t.name) for t in Team.query.order_by(Team.name).all()]
    if form.validate_on_submit():
        user.name = form.name.data.strip()
        user.email = form.email.data.lower().strip()
        user.role = form.role.data
        user.team_id = form.team_id.data if form.team_id.data != 0 else None
        user.phone = form.phone.data
        user.is_active = form.is_active.data
        if form.password.data:
            user.set_password(form.password.data)
        db.session.commit()
        flash(f'User {user.name} updated.', 'success')
        return redirect(url_for('admin.users'))
    form.team_id.data = user.team_id or 0
    return render_template('admin/user_form.html', form=form, title='Edit User', user=user)


@admin_bp.route('/users/<int:user_id>/toggle', methods=['POST'])
@admin_required
def user_toggle(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash('You cannot deactivate your own account.', 'danger')
    else:
        user.is_active = not user.is_active
        db.session.commit()
        status = 'activated' if user.is_active else 'deactivated'
        flash(f'User {user.name} {status}.', 'success')
    return redirect(url_for('admin.users'))


# ── Teams ──────────────────────────────────────────────────────────────────────

@admin_bp.route('/teams')
@leader_required
def teams():
    teams = Team.query.order_by(Team.name).all()
    return render_template('admin/teams.html', title='Teams', teams=teams)


@admin_bp.route('/teams/new', methods=['GET', 'POST'])
@admin_required
def team_new():
    form = TeamForm()
    leaders = User.query.filter(User.role.in_(['admin', 'team_leader'])).order_by(User.name).all()
    form.leader_id.choices = [(0, '— Select Leader —')] + [(u.id, u.name) for u in leaders]
    if form.validate_on_submit():
        team = Team(
            name=form.name.data.strip(),
            description=form.description.data,
            leader_id=form.leader_id.data if form.leader_id.data != 0 else None,
        )
        db.session.add(team)
        db.session.commit()
        flash(f'Team "{team.name}" created.', 'success')
        return redirect(url_for('admin.teams'))
    return render_template('admin/team_form.html', form=form, title='New Team', team=None)


@admin_bp.route('/teams/<int:team_id>/edit', methods=['GET', 'POST'])
@admin_required
def team_edit(team_id):
    team = Team.query.get_or_404(team_id)
    form = TeamForm(obj=team)
    leaders = User.query.filter(User.role.in_(['admin', 'team_leader'])).order_by(User.name).all()
    form.leader_id.choices = [(0, '— Select Leader —')] + [(u.id, u.name) for u in leaders]
    if form.validate_on_submit():
        team.name = form.name.data.strip()
        team.description = form.description.data
        team.leader_id = form.leader_id.data if form.leader_id.data != 0 else None
        db.session.commit()
        flash(f'Team "{team.name}" updated.', 'success')
        return redirect(url_for('admin.teams'))
    form.leader_id.data = team.leader_id or 0
    return render_template('admin/team_form.html', form=form, title='Edit Team', team=team)


# ── Clients ────────────────────────────────────────────────────────────────────

@admin_bp.route('/clients')
@leader_required
def clients():
    page = request.args.get('page', 1, type=int)
    clients = Client.query.order_by(Client.name).paginate(page=page, per_page=25, error_out=False)
    return render_template('admin/clients.html', title='Clients', clients=clients)


@admin_bp.route('/clients/new', methods=['GET', 'POST'])
@leader_required
def client_new():
    form = ClientForm()
    if form.validate_on_submit():
        existing = Client.query.filter_by(code=form.code.data.strip().upper()).first()
        if existing:
            flash('Client code already exists.', 'danger')
        else:
            client = Client(
                name=form.name.data.strip(),
                code=form.code.data.strip().upper(),
                contact_person=form.contact_person.data,
                email=form.email.data,
                phone=form.phone.data,
                address=form.address.data,
                gstin=form.gstin.data,
                is_active=form.is_active.data,
            )
            db.session.add(client)
            db.session.commit()
            flash(f'Client "{client.name}" created.', 'success')
            return redirect(url_for('admin.clients'))
    return render_template('admin/client_form.html', form=form, title='New Client', client=None)


@admin_bp.route('/clients/<int:client_id>/edit', methods=['GET', 'POST'])
@leader_required
def client_edit(client_id):
    client = Client.query.get_or_404(client_id)
    form = ClientForm(obj=client)
    if form.validate_on_submit():
        client.name = form.name.data.strip()
        client.code = form.code.data.strip().upper()
        client.contact_person = form.contact_person.data
        client.email = form.email.data
        client.phone = form.phone.data
        client.address = form.address.data
        client.gstin = form.gstin.data
        client.is_active = form.is_active.data
        db.session.commit()
        flash(f'Client "{client.name}" updated.', 'success')
        return redirect(url_for('admin.clients'))
    return render_template('admin/client_form.html', form=form, title='Edit Client', client=client)


# ── Task Categories ─────────────────────────────────────────────────────────────

@admin_bp.route('/categories')
@leader_required
def categories():
    cats = TaskCategory.query.order_by(TaskCategory.name).all()
    return render_template('admin/categories.html', title='Task Categories', categories=cats)


@admin_bp.route('/categories/new', methods=['GET', 'POST'])
@admin_required
def category_new():
    form = TaskCategoryForm()
    if form.validate_on_submit():
        cat = TaskCategory(
            name=form.name.data.strip(),
            description=form.description.data,
            color_code=form.color_code.data,
        )
        db.session.add(cat)
        db.session.commit()
        flash(f'Category "{cat.name}" created.', 'success')
        return redirect(url_for('admin.categories'))
    return render_template('admin/category_form.html', form=form, title='New Category', category=None)


@admin_bp.route('/categories/<int:cat_id>/edit', methods=['GET', 'POST'])
@admin_required
def category_edit(cat_id):
    cat = TaskCategory.query.get_or_404(cat_id)
    form = TaskCategoryForm(obj=cat)
    if form.validate_on_submit():
        cat.name = form.name.data.strip()
        cat.description = form.description.data
        cat.color_code = form.color_code.data
        db.session.commit()
        flash(f'Category "{cat.name}" updated.', 'success')
        return redirect(url_for('admin.categories'))
    return render_template('admin/category_form.html', form=form, title='Edit Category', category=cat)
