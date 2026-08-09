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
    from db import execute, active_connection
    if user_id is None:
        user_id = session.get('user_id')
    username = session.get('username', 'system')
    sql = '''
        INSERT INTO audit_log (action, entity_type, entity_id, details, user_id, username)
        VALUES (?, ?, ?, ?, ?, ?)
    '''
    params = (action, entity_type, entity_id, details, user_id, username)
    try:
        conn = active_connection()
        if conn is not None:
            cur = conn.cursor()
            try:
                cur.execute('SAVEPOINT audit_log_sp')
                cur.execute(sql, params)
                cur.execute('RELEASE SAVEPOINT audit_log_sp')
            except Exception:
                try:
                    cur.execute('ROLLBACK TO SAVEPOINT audit_log_sp')
                except Exception:
                    pass
                raise
        else:
            execute(sql, params)
    except Exception as e:
        logger.error(f"Failed to log audit: {e}")


def build_change_details(summary: str, old_values: dict, new_values: dict, labels: dict) -> str:
    """Diff old vs new values and return a JSON string for the audit log details.
    Only fields whose value changed are included."""
    import json
    changes = []
    for field, label in labels.items():
        ov = old_values.get(field)
        nv = new_values.get(field)
        if ov is None:
            ov = ''
        if nv is None:
            nv = ''
        if str(ov).strip() != str(nv).strip():
            changes.append({'field': field, 'label': label,
                            'old': str(ov), 'new': str(nv)})
    if not changes:
        return summary
    return json.dumps({'summary': summary, 'changes': changes}, ensure_ascii=False)


def parse_change_details(details: Optional[str]) -> Optional[dict]:
    """Parse audit log details into {summary, changes} if it is JSON, else None."""
    if not details:
        return None
    try:
        import json
        data = json.loads(details)
        if isinstance(data, dict) and 'changes' in data:
            return data
    except Exception:
        pass
    return None


def get_app_setting(key: str, default: str = None) -> str:
    from db import query_one
    row = query_one('SELECT value FROM app_settings WHERE key = ?', (key,))
    return row['value'] if row and row['value'] is not None else default


def set_app_setting(key: str, value: str):
    from db import get_db
    with get_db() as conn:
        conn.cursor().execute('''
            INSERT INTO app_settings (key, value) VALUES (?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
        ''', (key, str(value)))


def auto_archive_inactive_products(months: int = None) -> list:
    """Archive products with no movement (or no update) since `months` months ago.
    Returns list of (code, name) tuples that were archived."""
    from db import get_db, query_one
    from config import AUTO_ARCHIVE_INACTIVE_MONTHS
    if months is None:
        months = int(get_app_setting('auto_archive_months', str(AUTO_ARCHIVE_INACTIVE_MONTHS)))
    cutoff = (datetime.now() - timedelta(days=30 * months)).strftime('%Y-%m-%d %H:%M:%S')
    archived = []
    with get_db() as conn:
        cursor = conn.cursor()
        rows = cursor.execute('''
            SELECT id, code, name FROM products p
            WHERE deleted_at IS NULL
              AND COALESCE(
                    (SELECT MAX(sm.created_at) FROM stock_movements sm WHERE sm.product_id = p.id),
                    p.updated_at
                  ) < ?
        ''', (cutoff,)).fetchall()
        for r in rows:
            cursor.execute('UPDATE products SET deleted_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE id = ?', (r['id'],))
            archived.append((r['code'], r['name']))
    for code, name in archived:
        log_audit('delete', 'product', None, f"Archivage auto (inactif): {code} - {name}")
    return archived


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
