import logging
from flask import render_template, request, redirect, url_for, session, flash, jsonify
from db import get_db, query, query_one, execute
from utils import admin_required, principal_admin_required, get_translation, log_audit
from translations import TRANSLATIONS

logger = logging.getLogger(__name__)


def register_workshop_routes(app):

    @app.route('/workshops')
    @admin_required
    def workshops():
        search = request.args.get('search', '')
        if search:
            rows = query('SELECT * FROM workshops WHERE name LIKE ? OR city LIKE ? ORDER BY name', (f'%{search}%', f'%{search}%'))
        else:
            rows = query('SELECT * FROM workshops ORDER BY name')
        return render_template('workshops.html', workshops=rows,
                             search=search,
                             translations=TRANSLATIONS[session.get('lang', 'fr')],
                             lang=session.get('lang', 'fr'))

    @app.route('/add_workshop', methods=['GET', 'POST'])
    @admin_required
    def add_workshop():
        if request.method == 'POST':
            try:
                name = request.form['name'].strip()
                location = request.form.get('location', '').strip()
                city = request.form.get('city', '').strip()
                description = request.form.get('description', '').strip()
                with get_db() as conn:
                    cursor = conn.cursor()
                    cursor.execute('SELECT id FROM workshops WHERE name = ?', (name,))
                    if cursor.fetchone():
                        flash(get_translation('workshop_name') + ' existe déjà', 'error')
                        return render_template('add_workshop.html',
                                             translations=TRANSLATIONS[session.get('lang', 'fr')],
                                             lang=session.get('lang', 'fr'))
                    cursor.execute('''INSERT INTO workshops (name, location, city, description)
                                    VALUES (?, ?, ?, ?)''', (name, location, city, description))
                    log_audit('create', 'workshop', cursor.lastrowid, f"Création atelier {name}")
                flash(get_translation('workshop_added_successfully'), 'success')
                return redirect(url_for('workshops'))
            except Exception as e:
                logger.error(f"Error adding workshop: {e}")
                flash(f"Erreur: {str(e)}", 'error')
        return render_template('add_workshop.html',
                             translations=TRANSLATIONS[session.get('lang', 'fr')],
                             lang=session.get('lang', 'fr'))

    @app.route('/edit_workshop/<int:workshop_id>', methods=['GET', 'POST'])
    @admin_required
    def edit_workshop(workshop_id):
        with get_db() as conn:
            cursor = conn.cursor()
            if request.method == 'POST':
                try:
                    name = request.form['name'].strip()
                    location = request.form.get('location', '').strip()
                    city = request.form.get('city', '').strip()
                    description = request.form.get('description', '').strip()
                    active = 1 if 'active' in request.form else 0

                    cursor.execute('SELECT id FROM workshops WHERE name = ? AND id != ?', (name, workshop_id))
                    if cursor.fetchone():
                        flash(get_translation('workshop_name') + ' existe déjà', 'error')
                        return redirect(url_for('edit_workshop', workshop_id=workshop_id))

                    cursor.execute('''UPDATE workshops SET name=?, location=?, city=?, description=?, active=?
                                    WHERE id=?''', (name, location, city, description, active, workshop_id))
                    log_audit('update', 'workshop', workshop_id, f"Mise à jour atelier {name}")
                    flash(get_translation('workshop_updated_successfully'), 'success')
                    return redirect(url_for('workshops'))
                except Exception as e:
                    logger.error(f"Error updating workshop: {e}")
                    flash(f"Erreur: {str(e)}", 'error')

            cursor.execute('SELECT * FROM workshops WHERE id = ?', (workshop_id,))
            workshop = cursor.fetchone()
            if not workshop:
                flash(get_translation('workshop_not_found'), 'error')
                return redirect(url_for('workshops'))
        return render_template('edit_workshop.html', workshop=workshop,
                             translations=TRANSLATIONS[session.get('lang', 'fr')],
                             lang=session.get('lang', 'fr'))

    @app.route('/delete_workshop/<int:workshop_id>')
    @admin_required
    def delete_workshop(workshop_id):
        try:
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT COUNT(*) FROM users WHERE workshop_id = ?', (workshop_id,))
                if cursor.fetchone()[0] > 0:
                    flash(get_translation('workshop_has_users'), 'error')
                    return redirect(url_for('workshops'))
                cursor.execute('SELECT COUNT(*) FROM products WHERE workshop_id = ?', (workshop_id,))
                if cursor.fetchone()[0] > 0:
                    flash(get_translation('workshop_has_products'), 'error')
                    return redirect(url_for('workshops'))
                cursor.execute('DELETE FROM workshops WHERE id = ?', (workshop_id,))
                log_audit('delete', 'workshop', workshop_id, f"Suppression atelier #{workshop_id}")
            flash(get_translation('workshop_deleted_successfully'), 'success')
        except Exception as e:
            logger.error(f"Error deleting workshop: {e}")
            flash(f"Erreur: {str(e)}", 'error')
        return redirect(url_for('workshops'))

    @app.route('/api/workshops')
    @login_required
    def api_workshops():
        user_workshop_id = session.get('workshop_id')
        if session.get('role') in ('admin', 'principal_admin'):
            rows = query('SELECT id, name, city FROM workshops WHERE active = 1 ORDER BY name')
        else:
            rows = query('SELECT id, name, city FROM workshops WHERE id = ? AND active = 1 ORDER BY name', (user_workshop_id,))
        return jsonify([{'id': r['id'], 'name': r['name'], 'city': r['city']} for r in rows])


from utils import login_required