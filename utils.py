import os
from functools import wraps
from typing import Callable, Optional
from flask import session, redirect, url_for, flash
from config import ALLOWED_EXTENSIONS, LOGO_EXTENSIONS
from datetime import datetime, timedelta
from db import query_one

import logging
logger = logging.getLogger(__name__)


def excel_serial_to_datetime(excel_num: float):
    if excel_num < 1:
        raise ValueError("Invalid Excel serial date")
    base_date = datetime(1899, 12, 30)
    days = int(excel_num)
    seconds = int((excel_num - days) * 86400)
    return base_date + timedelta(days=days, seconds=seconds)


def allowed_file(filename: str, extensions: Optional[set] = None) -> bool:
    if extensions is None:
        extensions = ALLOWED_EXTENSIONS
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in extensions


def allowed_logo_file(filename: str) -> bool:
    return allowed_file(filename, LOGO_EXTENSIONS)


def allowed_excel_file(filename: str) -> bool:
    return allowed_file(filename, {'xlsx', 'xls'})


def login_required(f: Callable) -> Callable:
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f: Callable) -> Callable:
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        user = query_one('SELECT role FROM users WHERE id = ?', (session['user_id'],))
        if not user or user['role'] not in ('admin', 'principal_admin'):
            from translations import TRANSLATIONS
            flash(TRANSLATIONS[session.get('lang', 'fr')]['access_denied'], 'error')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function


def principal_admin_required(f: Callable) -> Callable:
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        user = query_one('SELECT role FROM users WHERE id = ?', (session['user_id'],))
        if not user or user['role'] != 'principal_admin':
            from translations import TRANSLATIONS
            flash(TRANSLATIONS[session.get('lang', 'fr')]['access_denied'], 'error')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated_function


def get_user_info(user_id: int) -> Optional[tuple]:
    from db import query_one
    user = query_one('SELECT username, email, role FROM users WHERE id = ?', (user_id,))
    return (user['username'], user['email'], user['role']) if user else None


def get_translation(key: str) -> str:
    from translations import TRANSLATIONS
    lang = session.get('lang', 'fr')
    return TRANSLATIONS.get(lang, {}).get(key, key)


def log_audit(action: str, entity_type: str, entity_id: int, details: str, user_id: int = None):
    from db import execute
    if user_id is None:
        user_id = session.get('user_id')
    username = session.get('username', 'system')
    try:
        execute('''
            INSERT INTO audit_log (action, entity_type, entity_id, details, user_id, username)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (action, entity_type, entity_id, details, user_id, username))
    except Exception as e:
        logger.error(f"Failed to log audit: {e}")


def workshop_filter(table_alias: str = None) -> tuple:
    """Returns (where_clause, params) for workshop scoping.
    Admins see ALL workshops. Regular users see only their assigned workshop."""
    role = session.get('role', 'user')
    if role in ('admin', 'principal_admin'):
        return ('', [])
    workshop_id = session.get('workshop_id')
    prefix = f'{table_alias}.' if table_alias else ''
    if workshop_id:
        return (f' AND {prefix}workshop_id = ?', [workshop_id])
    return (f' AND {prefix}workshop_id IS NULL', [])
