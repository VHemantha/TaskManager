import os
import uuid
from flask import render_template, request, jsonify, current_app, send_from_directory, abort
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from app.blueprints.chat import chat_bp
from app.models.chat import ChatMessage
from app.extensions import db, socketio


def _get_accessible_channels(user):
    """Return list of (channel_id, label) tuples the user may access.

    Admin          → all team channels + general
    Team Leader    → only their own team channel
    Team Member    → only their own team channel
    Client Manager → their team channel (if assigned) + general
    """
    from app.models.user import Team, ROLE_ADMIN, ROLE_CLIENT_MANAGER

    if user.role == ROLE_ADMIN:
        teams = Team.query.order_by(Team.name).all()
        channels = [('general', 'General')]
        for t in teams:
            channels.append((f'team_{t.id}', t.name))
        return channels

    if user.role == ROLE_CLIENT_MANAGER:
        channels = [('general', 'General')]
        if user.team_id:
            from app.models.user import Team
            team = Team.query.get(user.team_id)
            if team:
                channels.append((f'team_{user.team_id}', team.name))
        return channels

    # team_leader / team_member — only their team
    if user.team_id:
        from app.models.user import Team
        team = Team.query.get(user.team_id)
        label = team.name if team else f'Team {user.team_id}'
        return [(f'team_{user.team_id}', label)]

    # No team assigned — fallback to general
    return [('general', 'General')]


def _default_channel(user):
    channels = _get_accessible_channels(user)
    return channels[0][0] if channels else 'general'


def _can_access_channel(user, channel):
    """Return True if the user is allowed to read/write to this channel."""
    allowed = {ch for ch, _ in _get_accessible_channels(user)}
    return channel in allowed


@chat_bp.route('/assign')
@login_required
def assign():
    """Team chat page — accessible to all authenticated users."""
    from app.models.user import User, Team
    from app.models.client import Client
    from app.models.task import TaskCategory

    accessible_channels = _get_accessible_channels(current_user)

    # Allow admin to switch channels via ?channel= query param
    requested = request.args.get('channel', '')
    if requested and _can_access_channel(current_user, requested):
        channel = requested
    else:
        channel = _default_channel(current_user)

    messages = ChatMessage.query.filter_by(channel=channel)\
        .order_by(ChatMessage.created_at.desc()).limit(80).all()
    messages.reverse()

    # For the members panel — admin sees all, others see their team only
    from app.models.user import ROLE_ADMIN
    if current_user.role == ROLE_ADMIN:
        members = User.query.filter_by(is_active=True).order_by(User.name).all()
    elif current_user.team_id:
        members = User.query.filter_by(is_active=True, team_id=current_user.team_id)\
                            .order_by(User.name).all()
    else:
        members = [current_user]

    clients = Client.query.filter_by(is_active=True).order_by(Client.name).all()
    categories = TaskCategory.query.order_by(TaskCategory.name).all()

    return render_template(
        'chat/assign.html', title='Team Chat',
        channel=channel,
        accessible_channels=accessible_channels,
        messages=messages,
        members=members,
        clients=clients,
        categories=categories,
    )


@chat_bp.route('/send', methods=['POST'])
@login_required
def send_message():
    """HTTP POST for reliable plain-text message sending."""
    data = request.get_json()
    channel = (data or {}).get('channel', 'general')
    content = ((data or {}).get('content') or '').strip()

    if not content:
        return jsonify({'error': 'Empty message'}), 400

    if not _can_access_channel(current_user, channel):
        return jsonify({'error': 'Access denied to this channel'}), 403

    msg = ChatMessage(
        channel=channel,
        sender_id=current_user.id,
        content=content,
    )
    db.session.add(msg)
    db.session.commit()

    msg_dict = msg.to_dict()
    try:
        socketio.emit('new_message', msg_dict, room=channel, namespace='/chat')
    except Exception:
        pass
    return jsonify(msg_dict)


@chat_bp.route('/upload', methods=['POST'])
@login_required
def upload_file():
    """Upload a file to the team chat channel."""
    file = request.files.get('file')
    channel = request.form.get('channel', 'general')
    caption = (request.form.get('caption') or '').strip()

    if not file or file.filename == '':
        return jsonify({'error': 'No file selected'}), 400

    if not _can_access_channel(current_user, channel):
        return jsonify({'error': 'Access denied to this channel'}), 403

    allowed = current_app.config.get(
        'ALLOWED_EXTENSIONS',
        {'pdf', 'xlsx', 'xls', 'docx', 'doc', 'png', 'jpg', 'jpeg', 'zip', 'txt', 'csv'}
    )
    ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else ''
    if ext not in allowed:
        return jsonify({'error': f'File type ".{ext}" is not allowed'}), 400

    original_name = secure_filename(file.filename)
    unique_name = f'{uuid.uuid4().hex}_{original_name}'

    chat_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'chat')
    os.makedirs(chat_dir, exist_ok=True)
    filepath = os.path.join(chat_dir, unique_name)
    file.save(filepath)

    filesize = os.path.getsize(filepath)
    mimetype = file.mimetype or 'application/octet-stream'

    msg = ChatMessage(
        channel=channel,
        sender_id=current_user.id,
        content=caption if caption else f'Shared: {original_name}',
        attachment_filename=original_name,
        attachment_path=unique_name,
        attachment_size=filesize,
        attachment_mimetype=mimetype,
    )
    db.session.add(msg)
    db.session.commit()

    msg_dict = msg.to_dict()
    try:
        socketio.emit('new_message', msg_dict, room=channel, namespace='/chat')
    except Exception:
        pass
    return jsonify(msg_dict)


@chat_bp.route('/attachment/<path:filename>')
@login_required
def chat_attachment(filename):
    """Serve a chat file attachment (authenticated users only)."""
    chat_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], 'chat')
    safe_name = os.path.basename(filename)
    return send_from_directory(chat_dir, safe_name, as_attachment=False)


@chat_bp.route('/history')
@login_required
def history():
    """AJAX: load older messages for a channel."""
    channel = request.args.get('channel', 'general')
    if not _can_access_channel(current_user, channel):
        return jsonify({'error': 'Access denied'}), 403
    before_id = request.args.get('before_id', type=int)
    query = ChatMessage.query.filter_by(channel=channel)
    if before_id:
        query = query.filter(ChatMessage.id < before_id)
    messages = query.order_by(ChatMessage.created_at.desc()).limit(20).all()
    return jsonify([m.to_dict() for m in reversed(messages)])
