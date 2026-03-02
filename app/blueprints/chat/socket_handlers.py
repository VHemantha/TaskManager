from datetime import datetime, timezone
from flask import request
from flask_login import current_user
from flask_socketio import join_room, leave_room, emit
from app.extensions import db
from app.models.chat import ChatMessage
from app.models.task import Task, TaskAssignment, TaskStatusHistory
from app.models.user import User
from app.utils.helpers import generate_task_no
from app.utils.notifications import notify_task_assigned


def register_chat_handlers(socketio):

    @socketio.on('connect', namespace='/chat')
    def on_connect():
        if not current_user.is_authenticated:
            return False  # Reject unauthenticated connections

    @socketio.on('join_channel', namespace='/chat')
    def on_join_channel(data):
        channel = data.get('channel', 'general')
        join_room(channel)

    @socketio.on('leave_channel', namespace='/chat')
    def on_leave_channel(data):
        channel = data.get('channel', 'general')
        leave_room(channel)

    @socketio.on('send_message', namespace='/chat')
    def on_send_message(data):
        """Save a plain chat message and broadcast to channel."""
        if not current_user.is_authenticated:
            return
        channel = data.get('channel', 'general')
        content = data.get('content', '').strip()
        if not content:
            return

        msg = ChatMessage(
            channel=channel,
            sender_id=current_user.id,
            content=content,
        )
        db.session.add(msg)
        db.session.commit()

        emit('new_message', msg.to_dict(), room=channel, namespace='/chat')

    @socketio.on('parse_preview', namespace='/chat')
    def on_parse_preview(data):
        """Parse a tag message and return preview without committing."""
        if not current_user.is_authenticated:
            return
        text = data.get('text', '').strip()
        if not text:
            return
        from app.blueprints.chat.parser import parse_chat_message
        result = parse_chat_message(text, db.session)
        emit('task_preview', {
            'raw_message': result['raw_message'],
            'clean_message': result['clean_message'],
            'assignees': [{'id': u.id, 'name': u.name} for u in result['assignees']],
            'categories': result['categories'],
            'priority': result['priority'],
            'due_date': result['due_date'].strftime('%d %b %Y') if result['due_date'] else None,
            'client': {'id': result['client'].id, 'name': result['client'].name} if result['client'] else None,
            'estimated_hours': result['estimated_hours'],
        })

    @socketio.on('confirm_task', namespace='/chat')
    def on_confirm_task(data):
        """
        Create a task from confirmed parsed data and broadcast to channel.
        Expected data keys: channel, title, assignee_ids, category_name,
                            priority, due_date, client_id, estimated_hours, raw_message
        """
        if not current_user.is_authenticated:
            return
        if current_user.role not in ('admin', 'team_leader'):
            emit('error', {'message': 'Insufficient permissions'})
            return

        channel = data.get('channel', 'general')
        title = data.get('title') or data.get('clean_message', 'Untitled Task')
        assignee_ids = data.get('assignee_ids', [])
        priority = data.get('priority', 'medium')
        due_date_str = data.get('due_date')
        client_id = data.get('client_id')
        estimated_hours = data.get('estimated_hours')
        raw_message = data.get('raw_message', '')
        category_name = data.get('category_name')

        from app.models.task import TaskCategory
        category_id = None
        if category_name:
            cat = TaskCategory.query.filter_by(name=category_name.upper()).first()
            if not cat:
                cat = TaskCategory.query.filter(TaskCategory.name.ilike(f'%{category_name}%')).first()
            if cat:
                category_id = cat.id

        due_date = None
        if due_date_str:
            from app.utils.helpers import parse_date_tag
            due_date = parse_date_tag(due_date_str)

        task = Task(
            task_no=generate_task_no(),
            title=title.strip(),
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
            assn = TaskAssignment(task_id=task.id, user_id=uid, is_primary=(i == 0))
            db.session.add(assn)

        history = TaskStatusHistory(
            task_id=task.id, changed_by=current_user.id,
            old_status=None, new_status=task.status
        )
        db.session.add(history)

        # Save the originating chat message
        msg = ChatMessage(
            channel=channel,
            sender_id=current_user.id,
            content=raw_message,
            is_task_message=True,
            linked_task_id=task.id,
        )
        db.session.add(msg)
        db.session.commit()

        if assignee_ids:
            notify_task_assigned(task, assignee_ids)

        emit('task_created', {
            'task_id': task.id,
            'task_no': task.task_no,
            'title': task.title,
            'priority': task.priority,
            'status': task.status,
            'message': msg.to_dict(),
        }, room=channel, namespace='/chat')

    @socketio.on('typing', namespace='/chat')
    def on_typing(data):
        channel = data.get('channel', 'general')
        emit('user_typing', {
            'user_id': current_user.id,
            'name': current_user.get_display_name(),
        }, room=channel, include_self=False, namespace='/chat')
