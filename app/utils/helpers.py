import os
import uuid
import re
from datetime import datetime, timezone
from werkzeug.utils import secure_filename
from flask import current_app
from app.extensions import db


def generate_task_no():
    """Generate a unique task number like TASK-2026-00142."""
    from app.models.task import Task
    year = datetime.now(timezone.utc).year
    prefix = f'TASK-{year}-'
    last = db.session.query(Task).filter(
        Task.task_no.like(f'{prefix}%')
    ).order_by(Task.task_no.desc()).first()
    if last:
        try:
            seq = int(last.task_no.split('-')[-1]) + 1
        except (ValueError, IndexError):
            seq = 1
    else:
        seq = 1
    return f'{prefix}{seq:05d}'


def allowed_file(filename):
    """Check if a filename has an allowed extension."""
    allowed = current_app.config.get('ALLOWED_EXTENSIONS', set())
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed


def save_attachment(file, task_id):
    """Save an uploaded file and return (filename, filepath, filesize, mimetype)."""
    if not allowed_file(file.filename):
        raise ValueError(f'File type not allowed: {file.filename}')

    original_name = secure_filename(file.filename)
    unique_name = f'{uuid.uuid4().hex}_{original_name}'

    upload_base = current_app.config['UPLOAD_FOLDER']
    task_dir = os.path.join(upload_base, str(task_id))
    os.makedirs(task_dir, exist_ok=True)

    filepath = os.path.join(task_dir, unique_name)
    file.save(filepath)

    filesize = os.path.getsize(filepath)
    mimetype = file.mimetype or 'application/octet-stream'
    relative_path = os.path.join(str(task_id), unique_name).replace('\\', '/')

    return original_name, relative_path, filesize, mimetype


def parse_date_tag(date_str):
    """
    Parse a date string from a chat tag.
    Supports: '15Mar', '15Mar2026', '2026-03-15', '15/03/2026'
    Returns a datetime object or None.
    """
    date_str = date_str.strip()
    current_year = datetime.now(timezone.utc).year

    formats_with_year = [
        '%Y-%m-%d',
        '%d/%m/%Y',
        '%d-%m-%Y',
        '%d%b%Y',
        '%d%B%Y',
    ]
    formats_without_year = [
        '%d%b',
        '%d%B',
    ]

    for fmt in formats_with_year:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue

    for fmt in formats_without_year:
        try:
            dt = datetime.strptime(date_str, fmt)
            return dt.replace(year=current_year)
        except ValueError:
            continue

    return None


def parse_hours_tag(hours_str):
    """Parse '^4h' or '^1.5h' or '^2' → float hours."""
    hours_str = hours_str.strip().lower().rstrip('h')
    try:
        return float(hours_str)
    except ValueError:
        return None


def truncate(text, length=80):
    """Truncate a string to a given length."""
    if not text:
        return ''
    if len(text) <= length:
        return text
    return text[:length - 3] + '...'


def log_activity(task_id, user_id, action_type, detail=''):
    """Append a TaskActivity record. Caller must commit."""
    from app.models.activity import TaskActivity
    entry = TaskActivity(
        task_id=task_id,
        user_id=user_id,
        action_type=action_type,
        detail=detail,
    )
    db.session.add(entry)


def format_datetime(dt, fmt='%d %b %Y, %I:%M %p'):
    """Format a datetime for display."""
    if dt is None:
        return '—'
    return dt.strftime(fmt)
