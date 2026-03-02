import re
from app.utils.helpers import parse_date_tag, parse_hours_tag

# Regex patterns for chat tags
_RE_ASSIGNEE = re.compile(r'@(\w+)')
_RE_CATEGORY = re.compile(r'#(\w+)')
_RE_PRIORITY = re.compile(r'!(\w+)')
_RE_DUE_DATE = re.compile(r'~(\S+)')
_RE_CLIENT = re.compile(r'\$(\w+)')
_RE_HOURS = re.compile(r'\^([\d.]+)h?')

_PRIORITY_MAP = {
    'urgent': 'urgent', 'u': 'urgent',
    'high': 'high', 'h': 'high',
    'medium': 'medium', 'med': 'medium', 'm': 'medium', 'normal': 'medium',
    'low': 'low', 'l': 'low',
}


def parse_chat_message(text, db_session):
    """
    Parse a chat message for structured task tags.

    Returns a dict with keys:
      raw_message, clean_message, assignees, categories,
      priority, due_date, client, estimated_hours
    """
    from app.models.user import User
    from app.models.client import Client

    result = {
        'raw_message': text,
        'clean_message': text,
        'assignees': [],
        'categories': [],
        'priority': 'medium',
        'due_date': None,
        'client': None,
        'estimated_hours': None,
    }

    # --- @assignees ---
    assignee_tags = _RE_ASSIGNEE.findall(text)
    resolved_users = []
    for username in assignee_tags:
        user = db_session.query(User).filter(
            User.is_active == True,
            db.or_(
                User.name.ilike(f'%{username}%'),
                User.email.ilike(f'{username}%')
            )
        ).first()
        if user and user not in resolved_users:
            resolved_users.append(user)
    result['assignees'] = resolved_users

    # --- #categories ---
    result['categories'] = list({c.upper() for c in _RE_CATEGORY.findall(text)})

    # --- !priority ---
    priority_matches = _RE_PRIORITY.findall(text)
    if priority_matches:
        raw_p = priority_matches[0].lower()
        result['priority'] = _PRIORITY_MAP.get(raw_p, 'medium')

    # --- ~due_date ---
    date_matches = _RE_DUE_DATE.findall(text)
    if date_matches:
        result['due_date'] = parse_date_tag(date_matches[0])

    # --- $client ---
    client_matches = _RE_CLIENT.findall(text)
    if client_matches:
        code = client_matches[0].upper()
        client = db_session.query(Client).filter(
            Client.is_active == True,
            db.or_(
                Client.code.ilike(f'%{code}%'),
                Client.name.ilike(f'%{code}%')
            )
        ).first()
        result['client'] = client

    # --- ^hours ---
    hours_matches = _RE_HOURS.findall(text)
    if hours_matches:
        result['estimated_hours'] = parse_hours_tag(hours_matches[0])

    # --- Clean message (remove all tags) ---
    clean = text
    clean = _RE_ASSIGNEE.sub('', clean)
    clean = _RE_CATEGORY.sub('', clean)
    clean = _RE_PRIORITY.sub('', clean)
    clean = _RE_DUE_DATE.sub('', clean)
    clean = _RE_CLIENT.sub('', clean)
    clean = _RE_HOURS.sub('', clean)
    result['clean_message'] = ' '.join(clean.split())  # collapse whitespace

    return result


# Import db here to avoid circular imports
from app.extensions import db
