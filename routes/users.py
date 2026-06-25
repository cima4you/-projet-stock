import logging
from flask import render_template, request, redirect, url_for, session, flash
from werkzeug.security import generate_password_hash
from db import get_db, query
from utils import admin_required, principal_admin_required, get_translation, log_audit
from translations import TRANSLATIONS

logger = logging.getLogger(__name__)


def register_user_routes(app):

    @app.route('/users')
    @admin_required
    def users():
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT u.id, u.username, u.email, u.role, u.active, u.created_at, u.last_login, u.workshop_id, COALESCE(w.name, '') as workshop_name
                FROM users u
                LEFT JOIN workshops w ON u.workshop_id = w.id
                ORDER BY u.created_at DESC
            ''')
            users_list = cursor.fetchall()
        return render_template('users.html', users=users_list,
                             translations=TRANSLATIONS[session.get('lang', 'fr')],
                             lang=session.get('lang', 'fr'))

    @app.route('/add_user', methods=['GET', 'POST'])
    @admin_required
    def add_user():
        if request.method == 'POST':
            try:
                username = request.form['username'].strip()
                email = request.form['email'].strip()
                password = request.form['password']
                role = request.form['role']
                workshop_id = request.form.get('workshop_id', '') or None
                if workshop_id:
                    workshop_id = int(workshop_id)
                if role == 'principal_admin':
                    flash(get_translation('cannot_create_principal_admin'), 'error')
                    workshops = query('SELECT id, name, city FROM workshops WHERE active = 1 ORDER BY name')
                    return render_template('add_user.html',
                                         workshops=workshops,
                                         translations=TRANSLATIONS[session.get('lang', 'fr')],
                                         lang=session.get('lang', 'fr'))
                with get_db() as conn:
                    cursor = conn.cursor()
                    cursor.execute('SELECT id FROM users WHERE username = ? OR email = ?', (username, email))
                    if cursor.fetchone():
                        flash(get_translation('username_or_email_already_exists'), 'error')
                        workshops = query('SELECT id, name, city FROM workshops WHERE active = 1 ORDER BY name')
                        return render_template('add_user.html',
                                             workshops=workshops,
                                             translations=TRANSLATIONS[session.get('lang', 'fr')],
                                             lang=session.get('lang', 'fr'))
                    password_hash = generate_password_hash(password)
                    cursor.execute('INSERT INTO users (username, password_hash, email, role, workshop_id) VALUES (?, ?, ?, ?, ?)',
                                  (username, password_hash, email, role, workshop_id))
                    log_audit('create', 'user', cursor.lastrowid, f"Création utilisateur {username} ({role})")
                flash(get_translation('user_added_successfully'), 'success')
                return redirect(url_for('users'))
            except Exception as e:
                logger.error(f"Error adding user: {e}")
                flash(f"Erreur lors de l'ajout: {str(e)}", 'error')
        workshops = query('SELECT id, name, city FROM workshops WHERE active = 1 ORDER BY name')
        return render_template('add_user.html',
                             workshops=workshops,
                             translations=TRANSLATIONS[session.get('lang', 'fr')],
                             lang=session.get('lang', 'fr'))

    @app.route('/edit_user/<int:user_id>', methods=['GET', 'POST'])
    @principal_admin_required
    def edit_user(user_id):
        with get_db() as conn:
            cursor = conn.cursor()
            if request.method == 'POST':
                try:
                    username = request.form['username'].strip()
                    email = request.form['email'].strip()
                    role = request.form['role']
                    active = 1 if 'active' in request.form else 0
                    new_password = request.form.get('new_password', '').strip()
                    workshop_id = request.form.get('workshop_id', '') or None
                    if workshop_id:
                        workshop_id = int(workshop_id)

                    cursor.execute('SELECT role FROM users WHERE id = ?', (session['user_id'],))
                    result = cursor.fetchone()
                    if not result:
                        flash(get_translation('user_not_found'), 'error')
                        return redirect(url_for('users'))
                    current_user_role = result['role']

                    cursor.execute('SELECT id, role FROM users WHERE id = ?', (user_id,))
                    target_user = cursor.fetchone()
                    if not target_user:
                        flash(get_translation('user_not_found'), 'error')
                        return redirect(url_for('users'))
                    target_user_role = target_user['role']

                    if target_user_role == 'principal_admin':
                        if role != 'principal_admin':
                            flash(get_translation('cannot_demote_principal_admin'), 'error')
                            return redirect(url_for('edit_user', user_id=user_id))
                        if not active:
                            flash(get_translation('cannot_deactivate_principal_admin'), 'error')
                            return redirect(url_for('edit_user', user_id=user_id))
                        if new_password and current_user_role != 'principal_admin':
                            flash(get_translation('cannot_change_principal_admin_password'), 'error')
                            return redirect(url_for('edit_user', user_id=user_id))

                    if role == 'principal_admin' and current_user_role != 'principal_admin':
                        flash(get_translation('cannot_promote_to_principal_admin'), 'error')
                        return redirect(url_for('edit_user', user_id=user_id))

                    cursor.execute('SELECT id FROM users WHERE (username = ? OR email = ?) AND id != ?',
                                  (username, email, user_id))
                    if cursor.fetchone():
                        flash(get_translation('username_or_email_already_exists'), 'error')
                        return redirect(url_for('edit_user', user_id=user_id))

                    if new_password:
                        pw_hash = generate_password_hash(new_password)
                        cursor.execute('''UPDATE users SET username=?, email=?, role=?, active=?, workshop_id=?, password_hash=?
                                        WHERE id=?''', (username, email, role, active, workshop_id, pw_hash, user_id))
                    else:
                        cursor.execute('''UPDATE users SET username=?, email=?, role=?, active=?, workshop_id=?
                                        WHERE id=?''', (username, email, role, active, workshop_id, user_id))

                    log_audit('update', 'user', user_id, f"Mise à jour utilisateur {username} (role={role}, active={active})")
                    flash(get_translation('user_updated_successfully'), 'success')
                    return redirect(url_for('users'))
                except Exception as e:
                    logger.error(f"Error updating user: {e}")
                    flash(f"Erreur: {str(e)}", 'error')

            cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))
            user = cursor.fetchone()
            if not user:
                flash(get_translation('user_not_found'), 'error')
                return redirect(url_for('users'))
        workshops = query('SELECT id, name, city FROM workshops WHERE active = 1 ORDER BY name')
        return render_template('edit_user.html', user=user, workshops=workshops,
                             translations=TRANSLATIONS[session.get('lang', 'fr')],
                             lang=session.get('lang', 'fr'))

    @app.route('/delete_user/<int:user_id>')
    @admin_required
    def delete_user(user_id):
        if user_id == session['user_id']:
            flash(get_translation('cannot_delete_own_account'), 'error')
            return redirect(url_for('users'))
        try:
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT role FROM users WHERE id = ?', (user_id,))
                user = cursor.fetchone()
                if user and user['role'] == 'principal_admin':
                    flash(get_translation('cannot_delete_principal_admin'), 'error')
                    return redirect(url_for('users'))
                cursor.execute('DELETE FROM users WHERE id = ?', (user_id,))
                log_audit('delete', 'user', user_id, f"Suppression utilisateur #{user_id}")
            flash("Utilisateur supprimé avec succès", 'success')
        except Exception as e:
            logger.error(f"Error deleting user: {e}")
            flash(f"Erreur: {str(e)}", 'error')
        return redirect(url_for('users'))
