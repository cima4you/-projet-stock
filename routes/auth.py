import secrets
import time
from datetime import datetime, timedelta
from flask import render_template, request, redirect, url_for, session, flash
from werkzeug.security import check_password_hash, generate_password_hash
from db import get_db, query_one
from utils import get_translation
from notifications import send_password_reset_email
from translations import TRANSLATIONS


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
            now = time.time()
            attempts = session.get('login_attempts', [])
            attempts = [t for t in attempts if now - t < 300]
            if len(attempts) >= 5:
                flash("Trop de tentatives. Réessayez dans 5 minutes.", 'error')
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
                    session['user_id'] = user['id']
                    session['username'] = username
                    session['role'] = user['role']
                    session['workshop_id'] = user['workshop_id'] if 'workshop_id' in user.keys() and user['workshop_id'] else None
                    session['lang'] = session.get('lang', 'fr')
                    if session.get('workshop_id'):
                        ws = query_one('SELECT name FROM workshops WHERE id = ?', (session['workshop_id'],))
                        session['workshop_name'] = ws['name'] if ws else None
                    cursor.execute('UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE id = ?', (user['id'],))
                    flash(get_translation('login_successful'), 'success')
                    return redirect(url_for('dashboard'))
                else:
                    attempts = session.get('login_attempts', [])
                    attempts.append(time.time())
                    session['login_attempts'] = attempts
                    flash(get_translation('invalid_credentials'), 'error')
        return render_template('login.html',
                             translations=TRANSLATIONS[session.get('lang', 'fr')],
                             lang=session.get('lang', 'fr'))

    @app.route('/logout')
    def logout():
        session.clear()
        flash(get_translation('logged_out_successfully'), 'success')
        return redirect(url_for('login'))

    @app.route('/change_language/<lang>')
    def change_language(lang):
        if lang in ('ar', 'fr'):
            session['lang'] = lang
        return redirect(request.referrer or url_for('index'))

    @app.route('/forgot_password', methods=['GET', 'POST'])
    def forgot_password():
        if request.method == 'POST':
            email = request.form['email'].strip()
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT id FROM users WHERE email = ? AND active = 1', (email,))
                user = cursor.fetchone()
                if user:
                    reset_token = secrets.token_urlsafe(32)
                    expires_at = datetime.now() + timedelta(hours=1)
                    cursor.execute('UPDATE users SET reset_token = ?, reset_token_expires = ? WHERE id = ?',
                                   (reset_token, expires_at, user['id']))
                    send_password_reset_email(email, reset_token, session.get('lang', 'fr'))
                    flash(get_translation('password_reset_email_sent'), 'success')
                else:
                    flash(get_translation('password_reset_email_sent'), 'success')
            return redirect(url_for('login'))
        return render_template('forgot_password.html',
                             translations=TRANSLATIONS[session.get('lang', 'fr')],
                             lang=session.get('lang', 'fr'))

    @app.route('/reset_password/<token>', methods=['GET', 'POST'])
    def reset_password(token):
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id FROM users
                WHERE reset_token = ? AND reset_token_expires > ? AND active = 1
            ''', (token, datetime.now()))
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
                if len(password) < 6:
                    flash(get_translation('password_too_short'), 'error')
                    return render_template('reset_password.html', token=token,
                                         translations=TRANSLATIONS[session.get('lang', 'fr')],
                                         lang=session.get('lang', 'fr'))
                password_hash = generate_password_hash(password)
                cursor.execute('''
                    UPDATE users SET password_hash = ?, reset_token = NULL, reset_token_expires = NULL
                    WHERE id = ?
                ''', (password_hash, user['id']))
                flash(get_translation('password_reset_successful'), 'success')
                return redirect(url_for('login'))
        return render_template('reset_password.html', token=token,
                             translations=TRANSLATIONS[session.get('lang', 'fr')],
                             lang=session.get('lang', 'fr'))
