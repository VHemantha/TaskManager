from datetime import datetime, timezone
from app.extensions import db


class TaskComment(db.Model):
    __tablename__ = 'task_comments'

    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('tasks.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc),
                           onupdate=lambda: datetime.now(timezone.utc))
    is_edited = db.Column(db.Boolean, default=False)

    task = db.relationship('Task', back_populates='comments')
    author = db.relationship('User', backref='task_comments', lazy='select')

    def __repr__(self):
        return f'<TaskComment task={self.task_id} by={self.user_id}>'


class TaskAttachment(db.Model):
    __tablename__ = 'task_attachments'

    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey('tasks.id'), nullable=False)
    uploaded_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    filename = db.Column(db.String(255), nullable=False)
    filepath = db.Column(db.String(500), nullable=False)
    filesize = db.Column(db.Integer, nullable=True)  # bytes
    mimetype = db.Column(db.String(100), nullable=True)
    uploaded_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    task = db.relationship('Task', back_populates='attachments')
    uploader = db.relationship('User', backref='uploaded_files', lazy='select')

    @property
    def filesize_display(self):
        if self.filesize is None:
            return 'Unknown'
        if self.filesize < 1024:
            return f'{self.filesize} B'
        if self.filesize < 1024 * 1024:
            return f'{self.filesize / 1024:.1f} KB'
        return f'{self.filesize / (1024 * 1024):.1f} MB'

    def __repr__(self):
        return f'<TaskAttachment {self.filename}>'


class ChatMessage(db.Model):
    """General chat messages in the assignment interface (not task-specific comments)."""
    __tablename__ = 'chat_messages'

    id = db.Column(db.Integer, primary_key=True)
    channel = db.Column(db.String(100), nullable=False, index=True)  # e.g. 'general', 'team_1'
    sender_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    content = db.Column(db.Text, nullable=False)
    reply_to_id = db.Column(db.Integer, db.ForeignKey('chat_messages.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    is_pinned = db.Column(db.Boolean, default=False)
    is_task_message = db.Column(db.Boolean, default=False)  # True = task was created from this
    linked_task_id = db.Column(db.Integer, db.ForeignKey('tasks.id'), nullable=True)

    # File attachment support
    attachment_filename = db.Column(db.String(255), nullable=True)
    attachment_path = db.Column(db.String(500), nullable=True)   # relative to UPLOAD_FOLDER
    attachment_size = db.Column(db.Integer, nullable=True)        # bytes
    attachment_mimetype = db.Column(db.String(100), nullable=True)

    sender = db.relationship('User', backref='chat_messages', lazy='select')
    reply_to = db.relationship('ChatMessage', remote_side=[id], lazy='select')
    linked_task = db.relationship('Task', backref='source_messages', lazy='select')

    @property
    def attachment_size_display(self):
        if self.attachment_size is None:
            return ''
        if self.attachment_size < 1024:
            return f'{self.attachment_size} B'
        if self.attachment_size < 1024 * 1024:
            return f'{self.attachment_size / 1024:.1f} KB'
        return f'{self.attachment_size / (1024 * 1024):.1f} MB'

    def to_dict(self):
        return {
            'id': self.id,
            'channel': self.channel,
            'sender_id': self.sender_id,
            'sender_name': self.sender.get_display_name() if self.sender else 'Unknown',
            'sender_initials': self.sender.get_initials() if self.sender else '??',
            'content': self.content,
            'reply_to_id': self.reply_to_id,
            'created_at': self.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            'is_pinned': self.is_pinned,
            'is_task_message': self.is_task_message,
            'linked_task_id': self.linked_task_id,
            'attachment_filename': self.attachment_filename,
            'attachment_path': self.attachment_path,
            'attachment_size_display': self.attachment_size_display,
            'attachment_mimetype': self.attachment_mimetype or '',
        }

    def __repr__(self):
        return f'<ChatMessage channel={self.channel} by={self.sender_id}>'
