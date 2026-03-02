from datetime import datetime, timezone
from flask import jsonify, request, session, url_for
from flask_login import login_required, current_user
from app.blueprints.api import api_bp
from app.extensions import db
from app.models.user import User
from app.models.client import Client
from app.models.task import TaskCategory, Task
from app.models.notification import Notification


@api_bp.route('/users/search')
@login_required
def users_search():
    q = request.args.get('q', '').strip()
    if len(q) < 1:
        return jsonify([])
    users = User.query.filter(
        User.is_active == True,
        db.or_(User.name.ilike(f'%{q}%'), User.email.ilike(f'%{q}%'))
    ).order_by(User.name).limit(10).all()
    return jsonify([{
        'id': u.id,
        'name': u.name,
        'email': u.email,
        'role': u.get_role_label(),
        'initials': u.get_initials(),
    } for u in users])


@api_bp.route('/clients/search')
@login_required
def clients_search():
    q = request.args.get('q', '').strip()
    if len(q) < 1:
        return jsonify([])
    clients = Client.query.filter(
        Client.is_active == True,
        db.or_(Client.name.ilike(f'%{q}%'), Client.code.ilike(f'%{q}%'))
    ).order_by(Client.name).limit(10).all()
    return jsonify([{
        'id': c.id,
        'name': c.name,
        'code': c.code,
    } for c in clients])


@api_bp.route('/categories')
@login_required
def categories():
    cats = TaskCategory.query.order_by(TaskCategory.name).all()
    return jsonify([{
        'id': c.id,
        'name': c.name,
        'color_code': c.color_code,
    } for c in cats])


@api_bp.route('/chat/parse', methods=['POST'])
@login_required
def chat_parse():
    from app.blueprints.chat.parser import parse_chat_message
    from app.extensions import db as database
    data = request.get_json()
    text = data.get('text', '').strip()
    if not text:
        return jsonify({'error': 'No text provided'}), 400
    result = parse_chat_message(text, database.session)
    # Serialize for JSON
    output = {
        'raw_message': result['raw_message'],
        'clean_message': result['clean_message'],
        'assignees': [{'id': u.id, 'name': u.name, 'initials': u.get_initials()} for u in result['assignees']],
        'categories': result['categories'],
        'priority': result['priority'],
        'due_date': result['due_date'].strftime('%Y-%m-%d %H:%M') if result['due_date'] else None,
        'client': {'id': result['client'].id, 'name': result['client'].name, 'code': result['client'].code}
                  if result['client'] else None,
        'estimated_hours': result['estimated_hours'],
    }
    return jsonify(output)


@api_bp.route('/tasks/<int:task_id>/status-history')
@login_required
def task_status_history(task_id):
    from app.models.task import TaskStatusHistory, STATUS_LABELS
    history = TaskStatusHistory.query.filter_by(task_id=task_id)\
        .order_by(TaskStatusHistory.changed_at.desc()).all()
    return jsonify([{
        'old_status': h.old_status,
        'new_status': h.new_status,
        'old_label': STATUS_LABELS.get(h.old_status, '—') if h.old_status else '—',
        'new_label': STATUS_LABELS.get(h.new_status, h.new_status),
        'changed_by': h.changed_by_user.get_display_name() if h.changed_by_user else 'System',
        'changed_at': h.changed_at.strftime('%d %b %Y, %I:%M %p'),
        'notes': h.notes or '',
    } for h in history])


@api_bp.route('/notifications/unread-count')
@login_required
def notif_unread_count():
    count = Notification.query.filter_by(user_id=current_user.id, is_read=False).count()
    return jsonify({'count': count})


@api_bp.route('/tasks/from-chat', methods=['POST'])
@login_required
def create_task_from_chat():
    """Create a task from the chat assign interface via HTTP POST (reliable alternative to SocketIO)."""
    from app.models.task import TaskAssignment, TaskStatusHistory
    from app.models.chat import ChatMessage
    from app.utils.helpers import generate_task_no, parse_date_tag
    from app.utils.notifications import notify_task_assigned
    from app.extensions import socketio

    if current_user.role not in ('admin', 'team_leader'):
        return jsonify({'error': 'Insufficient permissions'}), 403

    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    channel = data.get('channel', 'general')
    title = (data.get('title') or data.get('clean_message') or '').strip()
    if not title:
        return jsonify({'error': 'Task title is required'}), 400

    assignee_ids = data.get('assignee_ids', [])
    priority = data.get('priority', 'medium')
    due_date_str = data.get('due_date')
    client_id = data.get('client_id')
    estimated_hours = data.get('estimated_hours')
    raw_message = data.get('raw_message', '')
    category_name = data.get('category_name')

    category_id = None
    if category_name:
        cat = TaskCategory.query.filter_by(name=category_name.upper()).first()
        if not cat:
            cat = TaskCategory.query.filter(TaskCategory.name.ilike(f'%{category_name}%')).first()
        if cat:
            category_id = cat.id

    due_date = None
    if due_date_str:
        due_date = parse_date_tag(due_date_str)

    task = Task(
        task_no=generate_task_no(),
        title=title,
        category_id=category_id,
        client_id=client_id if client_id else None,
        assigned_by=current_user.id,
        priority=priority,
        status='assigned' if assignee_ids else 'unassigned',
        due_date=due_date,
        estimated_hours=float(estimated_hours) if estimated_hours else None,
    )
    db.session.add(task)
    db.session.flush()

    for i, uid in enumerate(assignee_ids):
        assn = TaskAssignment(task_id=task.id, user_id=int(uid), is_primary=(i == 0))
        db.session.add(assn)

    history = TaskStatusHistory(
        task_id=task.id, changed_by=current_user.id,
        old_status=None, new_status=task.status
    )
    db.session.add(history)

    msg = ChatMessage(
        channel=channel,
        sender_id=current_user.id,
        content=raw_message or title,
        is_task_message=True,
        linked_task_id=task.id,
    )
    db.session.add(msg)
    db.session.commit()

    if assignee_ids:
        notify_task_assigned(task, [int(uid) for uid in assignee_ids])

    # Broadcast to chat room via SocketIO
    try:
        socketio.emit('task_created', {
            'task_id': task.id,
            'task_no': task.task_no,
            'title': task.title,
            'message': msg.to_dict(),
        }, room=channel, namespace='/chat')
    except Exception:
        pass  # SocketIO broadcast is best-effort; task is already saved

    return jsonify({
        'success': True,
        'task_id': task.id,
        'task_no': task.task_no,
        'task_url': f'/tasks/{task.id}',
    })


# ── Global Search ─────────────────────────────────────────────────────────────

@api_bp.route('/search')
@login_required
def global_search():
    from app.models.goal import Goal
    from app.models.sprint import Sprint
    q = request.args.get('q', '').strip()
    if len(q) < 2:
        return jsonify([])
    results = []
    tasks = Task.query.filter(
        db.or_(Task.title.ilike(f'%{q}%'), Task.task_no.ilike(f'%{q}%'))
    ).limit(5).all()
    for t in tasks:
        results.append({
            'type': 'task', 'icon': 'check2-square',
            'title': f'[{t.task_no}] {t.title[:50]}',
            'subtitle': t.status_label,
            'url': url_for('tasks.task_detail', task_id=t.id),
        })
    goals = Goal.query.filter(Goal.name.ilike(f'%{q}%')).limit(3).all()
    for g in goals:
        results.append({
            'type': 'goal', 'icon': 'trophy',
            'title': g.name[:50], 'subtitle': g.status_label,
            'url': url_for('goals.detail', goal_id=g.id),
        })
    sprints = Sprint.query.filter(Sprint.name.ilike(f'%{q}%')).limit(3).all()
    for s in sprints:
        results.append({
            'type': 'sprint', 'icon': 'lightning',
            'title': s.name[:50], 'subtitle': s.status_label,
            'url': url_for('sprints.board', sprint_id=s.id),
        })
    return jsonify(results)


@api_bp.route('/tasks/search')
@login_required
def tasks_search():
    q = request.args.get('q', '').strip()
    if len(q) < 1:
        return jsonify([])
    tasks = Task.query.filter(
        db.or_(Task.title.ilike(f'%{q}%'), Task.task_no.ilike(f'%{q}%'))
    ).limit(10).all()
    return jsonify([{
        'id': t.id, 'task_no': t.task_no,
        'title': t.title, 'status': t.status_label,
    } for t in tasks])


# ── Live Timer ────────────────────────────────────────────────────────────────

@api_bp.route('/timer/start', methods=['POST'])
@login_required
def timer_start():
    data = request.get_json() or {}
    task_id = data.get('task_id')
    if not task_id:
        return jsonify({'error': 'task_id required'}), 400
    task = Task.query.get_or_404(task_id)
    session['active_timer'] = {
        'task_id': task_id,
        'task_no': task.task_no,
        'task_title': task.title[:50],
        'start_time': datetime.now(timezone.utc).isoformat(),
    }
    return jsonify({'success': True, 'task_id': task_id, 'task_no': task.task_no})


@api_bp.route('/timer/stop', methods=['POST'])
@login_required
def timer_stop():
    from app.models.time_log import TimeLog
    timer = session.pop('active_timer', None)
    if not timer:
        return jsonify({'error': 'No active timer'}), 400
    start = datetime.fromisoformat(timer['start_time'])
    now = datetime.now(timezone.utc)
    hours = round((now - start).total_seconds() / 3600, 2)
    if hours < 0.01:
        return jsonify({'error': 'Timer duration too short (min 36 seconds)'}), 400
    task_id = timer['task_id']
    log = TimeLog(task_id=task_id, user_id=current_user.id, hours=hours, description='Timer session')
    db.session.add(log)
    task = Task.query.get(task_id)
    if task:
        task.actual_hours = (task.actual_hours or 0) + hours
    db.session.commit()
    return jsonify({'success': True, 'hours': hours, 'log_id': log.id})


@api_bp.route('/timer/current')
@login_required
def timer_current():
    timer = session.get('active_timer')
    if not timer:
        return jsonify(None)
    return jsonify(timer)
