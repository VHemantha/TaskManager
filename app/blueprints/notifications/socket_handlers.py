from flask_login import current_user
from flask_socketio import join_room
from app.extensions import db
from app.models.notification import Notification


def register_notification_handlers(socketio):

    @socketio.on('connect', namespace='/notifications')
    def on_connect():
        if not current_user.is_authenticated:
            return False
        join_room(f'user_{current_user.id}')

    @socketio.on('mark_read', namespace='/notifications')
    def on_mark_read(data):
        notif_id = data.get('notif_id')
        if notif_id:
            notif = Notification.query.filter_by(
                id=notif_id, user_id=current_user.id
            ).first()
            if notif:
                notif.is_read = True
                db.session.commit()
        count = Notification.query.filter_by(
            user_id=current_user.id, is_read=False
        ).count()
        from flask_socketio import emit
        emit('unread_count', {'count': count})
