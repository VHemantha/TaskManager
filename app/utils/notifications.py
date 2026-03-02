from flask import current_app
from app.extensions import db, socketio, mail
from app.models.notification import (
    Notification,
    NOTIF_TASK_ASSIGNED, NOTIF_TASK_STATUS_CHANGED, NOTIF_TASK_COMMENT,
    NOTIF_TASK_DEADLINE, NOTIF_TASK_OVERDUE, NOTIF_TASK_ESCALATED,
    NOTIF_TASK_COMPLETED, NOTIF_FILE_UPLOADED,
)


def send_email(to_address, subject, body_text):
    """Send a plain-text email via Flask-Mail. Fails silently if unconfigured."""
    if not to_address:
        return
    try:
        from flask_mail import Message
        msg = Message(
            subject=subject,
            recipients=[to_address],
            body=body_text,
            sender=current_app.config.get('MAIL_DEFAULT_SENDER') or
                   current_app.config.get('MAIL_USERNAME', 'noreply@taskmanager.local'),
        )
        mail.send(msg)
    except Exception:
        pass  # Email is best-effort — don't break the app if mail isn't configured


def create_notification(user_id, notif_type, title, message=None, task_id=None):
    """Create a Notification record and push it via SocketIO."""
    notif = Notification(
        user_id=user_id,
        type=notif_type,
        title=title,
        message=message,
        task_id=task_id,
    )
    db.session.add(notif)
    db.session.flush()  # get id before commit

    # Push real-time notification
    emit_to_user(user_id, 'new_notification', notif.to_dict())
    return notif


def emit_to_user(user_id, event, data):
    """Emit a SocketIO event to a specific user's room."""
    try:
        socketio.emit(event, data, room=f'user_{user_id}', namespace='/notifications')
    except Exception:
        pass  # Gracefully skip if SocketIO is not connected


def notify_task_assigned(task, assignee_ids):
    """Notify all assigned users of a new task (in-app + email)."""
    from app.models.user import User
    for uid in assignee_ids:
        create_notification(
            user_id=uid,
            notif_type=NOTIF_TASK_ASSIGNED,
            title=f'New task assigned: {task.task_no}',
            message=task.title,
            task_id=task.id,
        )
        user = User.query.get(uid)
        if user and user.email:
            send_email(
                to_address=user.email,
                subject=f'[TaskManager] New task assigned: {task.task_no}',
                body_text=(
                    f'Hi {user.get_display_name()},\n\n'
                    f'A new task has been assigned to you:\n\n'
                    f'  Task No : {task.task_no}\n'
                    f'  Title   : {task.title}\n'
                    f'  Priority: {task.priority_label}\n'
                    f'  Due Date: {task.due_date.strftime("%d %b %Y") if task.due_date else "Not set"}\n\n'
                    f'Log in to view details.\n\nTaskManager'
                ),
            )


def notify_status_change(task, changed_by_id, leader_ids):
    """Notify task creator / leader of a status change (in-app + email)."""
    from app.models.user import User
    notified = set()
    for uid in leader_ids:
        if uid not in notified:
            create_notification(
                user_id=uid,
                notif_type=NOTIF_TASK_STATUS_CHANGED,
                title=f'Task {task.task_no} status updated',
                message=f'Status changed to: {task.status_label}',
                task_id=task.id,
            )
            user = User.query.get(uid)
            if user and user.email and uid != changed_by_id:
                send_email(
                    to_address=user.email,
                    subject=f'[TaskManager] {task.task_no} → {task.status_label}',
                    body_text=(
                        f'Hi {user.get_display_name()},\n\n'
                        f'Task {task.task_no} status has been updated:\n\n'
                        f'  Title : {task.title}\n'
                        f'  Status: {task.status_label}\n\n'
                        f'Log in to view details.\n\nTaskManager'
                    ),
                )
            notified.add(uid)


def notify_new_comment(task, commenter_id, participant_ids):
    """Notify all task participants of a new comment."""
    for uid in participant_ids:
        if uid != commenter_id:
            create_notification(
                user_id=uid,
                notif_type=NOTIF_TASK_COMMENT,
                title=f'New comment on {task.task_no}',
                message=task.title,
                task_id=task.id,
            )


def notify_file_uploaded(task, uploader_id, participant_ids):
    """Notify task participants of a new file upload."""
    for uid in participant_ids:
        if uid != uploader_id:
            create_notification(
                user_id=uid,
                notif_type=NOTIF_FILE_UPLOADED,
                title=f'File uploaded on {task.task_no}',
                message=task.title,
                task_id=task.id,
            )
