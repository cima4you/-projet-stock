import secrets
import time
import hashlib
import logging
from datetime import datetime, timedelta, timezone
from flask import render_template, request, redirect, url_for, session, flash
from werkzeug.security import check_password_hash, generate_password_hash
from db import get_db, query_one, execute
from utils import get_translation, validate_password_strength
from notifications import send_password_reset_email
from translations import TRANSLATIONS

logger = logging.getLogger(__name__)

LOGIN_LOCK_ATTEMPTS = 5
LOGIN_LOCK_WINDOW = 300  # seconds


def _utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _is_ip_locked(ip):
    cutoff = _utcnow() - timedelta(seconds=LOGIN_LOCK_WINDOW)
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            'SELECT COUNT(*) FROM login_attempts '
            'WHERE ip_address = ? AND attempted_at > ?',
            (ip, cutoff))
        count = cursor.fetchone()[0]
    return count >= LOGIN_LOCK_ATTEMPTS


def _record_failed_attempt(ip, cursor=None):
    cutoff = _utcnow() - timedelta(seconds=LOGIN_LOCK_WINDOW * 2)
    now = _utcnow()
    if cursor is not None:
        cursor.execute('INSERT INTO login_attempts (ip_address, attempted_at) VALUES (?, ?)', (ip, now))
        cursor.execute(
            'DELETE FROM login_attempts WHERE attempted_at <= ?',
            (cutoff,))
        return
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute('INSERT INTO login_attempts (ip_address, attempted_at) VALUES (?, ?)', (ip, now))
        cursor.execute(
            'DELETE FROM login_attempts WHERE attempted_at <= ?',
            (cutoff,))


def register_auth_routes(app):

    @app.route('/')
    def index():
        if 'user_id' in session:
            return redirect(url_for('dashboard'))
        return redirect(url_for('login'))

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        if request.method == 'POST':
            ip = request.remote_addr or 'unknown'
            if _is_ip_locked(ip):
                flash("Trop de tentatives depuis cette adresse IP. Réessayez dans 5 minutes.", 'error')
                return render_template('login.html',
                                     translations=TRANSLATIONS[session.get('lang', 'fr')],
                                     lang=session.get('lang', 'fr'))
            username = request.form['username']
            password = request.form['password']
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT id, password_hash, role, active, workshop_id FROM users WHERE username = ?', (username,))
                user = cursor.fetchone()
                if user and user['active'] == 1 and check_password_hash(user['password_hash'], password):
                    session.clear()
                    session['user_id'] = user['id']
                    session['username'] = username
                    session['role'] = user['role']
                    session['workshop_id'] = user['workshop_id'] if 'workshop_id' in user.keys() and user['workshop_id'] else None
                    session['lang'] = 'fr'
                    if session.get('workshop_id'):
                        ws = query_one('SELECT name FROM workshops WHERE id = ?', (session['workshop_id'],))
                        session['workshop_name'] = ws['name'] if ws else None
                    cursor.execute('UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?', (user['id'],))
                    cursor.execute('INSERT INTO login_logs (user_id, username, action, ip_address) VALUES (?, ?, ?, ?)',
                                   (user['id'], username, 'login', ip))
                    flash(get_translation('login_successful'), 'success')
                    return redirect(url_for('dashboard'))
                else:
                    cursor.execute('INSERT INTO login_logs (user_id, username, action, ip_address) VALUES (?, ?, ?, ?)',
                                   (user['id'] if user else None, username, 'login_failed', ip))
                    _record_failed_attempt(ip, cursor)
                    flash(get_translation('invalid_credentials'), 'error')
        return render_template('login.html',
                             translations=TRANSLATIONS[session.get('lang', 'fr')],
                             lang=session.get('lang', 'fr'))

    @app.route('/logout')
    def logout():
        user_id = session.get('user_id')
        username = session.get('username', 'system')
        ip = request.remote_addr or 'unknown'
        try:
            execute('INSERT INTO login_logs (user_id, username, action, ip_address) VALUES (?, ?, ?, ?)',
                    (user_id, username, 'logout', ip))
        except Exception as e:
            logger.error(f"Failed to log logout: {e}")
        session.clear()
        flash(get_translation('logged_out_successfully'), 'success')
        return redirect(url_for('login'))

    @app.route('/change_language/<lang>')
    def change_language(lang):
        session['lang'] = 'fr'
        return redirect(request.referrer or url_for('index'))

    @app.route('/forgot_password', methods=['GET', 'POST'])
    def forgot_password():
        if request.method == 'POST':
            email = request.form['email'].strip()
            user_found = False
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT id FROM users WHERE email = ? AND active = 1', (email,))
                user = cursor.fetchone()
                if user:
                    reset_token = secrets.token_urlsafe(32)
                    expires_at = datetime.now() + timedelta(hours=1)
                    token_hash = hashlib.sha256(reset_token.encode('utf-8')).hexdigest()
                    cursor.execute('UPDATE users SET reset_token = ?, reset_token_expires = ? WHERE id = ?',
                                   (token_hash, expires_at, user['id']))
                    try:
                        send_password_reset_email(email, reset_token)
                    except Exception as e:
                        logger.error(f"Failed to send password reset email: {e}")
                    user_found = True
                time.sleep(0.5 if not user_found else 0)
            flash(get_translation('password_reset_email_sent'), 'success')
            return redirect(url_for('login'))
        return render_template('forgot_password.html',
                             translations=TRANSLATIONS[session.get('lang', 'fr')],
                             lang=session.get('lang', 'fr'))

    @app.route('/reset_password/<token>', methods=['GET', 'POST'])
    def reset_password(token):
        token_hash = hashlib.sha256(token.encode('utf-8')).hexdigest()
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id FROM users
                WHERE reset_token = ? AND reset_token_expires > ? AND active = 1
            ''', (token_hash, datetime.now()))
            user = cursor.fetchone()
            if not user:
                flash(get_translation('invalid_or_expired_token'), 'error')
                return redirect(url_for('login'))
            if request.method == 'POST':
                password = request.form['password']
                confirm_password = request.form['confirm_password']
                if password != confirm_password:
                    flash(get_translation('passwords_do_not_match'), 'error')
                    return render_template('reset_password.html', token=token,
                                         translations=TRANSLATIONS[session.get('lang', 'fr')],
                                         lang=session.get('lang', 'fr'))
                pw_error = validate_password_strength(password)
                if pw_error:
                    flash(pw_error, 'error')
                    return render_template('reset_password.html', token=token,
                                         translations=TRANSLATIONS[session.get('lang', 'fr')],
                                         lang=session.get('lang', 'fr'))
                password_hash = generate_password_hash(password)
                cursor.execute('''
                    UPDATE users SET password_hash = ?, reset_token = NULL, reset_token_expires = NULL
                    WHERE id = ?
                ''', (password_hash, user['id']))
                session.clear()
                flash(get_translation('password_reset_successful'), 'success')
                return redirect(url_for('login'))
        return render_template('reset_password.html', token=token,
                             translations=TRANSLATIONS[session.get('lang', 'fr')],
                             lang=session.get('lang', 'fr'))
