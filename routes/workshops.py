import json
import logging
from datetime import datetime, timedelta
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

    @app.route('/delete_workshop/<int:workshop_id>', methods=['POST'])
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

    @app.route('/workshop_dashboard/<int:workshop_id>')
    @admin_required
    def workshop_dashboard(workshop_id):
        with get_db() as conn:
            cursor = conn.cursor()
            workshop = cursor.execute('SELECT * FROM workshops WHERE id = ?', (workshop_id,)).fetchone()
            if not workshop:
                flash(get_translation('workshop_not_found'), 'error')
                return redirect(url_for('workshops'))
            ws_id = workshop_id

            def scoped_products(field='quantity <= 10'):
                return cursor.execute(f'SELECT COUNT(*) as cnt FROM products WHERE deleted_at IS NULL AND workshop_id = ? AND {field}', (ws_id,)).fetchone()['cnt']

            total_products = cursor.execute('SELECT COUNT(*) as cnt FROM products WHERE deleted_at IS NULL AND workshop_id = ?', (ws_id,)).fetchone()['cnt']
            low_stock_items = scoped_products()
            zero_stock_count = cursor.execute('SELECT COUNT(*) FROM products WHERE deleted_at IS NULL AND workshop_id = ? AND quantity = 0', (ws_id,)).fetchone()[0]
            total_movements = cursor.execute('SELECT COUNT(*) as cnt FROM stock_movements sm WHERE sm.workshop_id = ?', (ws_id,)).fetchone()['cnt']
            total_entries = cursor.execute('SELECT COUNT(*) as cnt FROM stock_movements sm WHERE sm.workshop_id = ? AND sm.movement_type = "entry"', (ws_id,)).fetchone()['cnt']
            total_exits = cursor.execute('SELECT COUNT(*) as cnt FROM stock_movements sm WHERE sm.workshop_id = ? AND sm.movement_type = "exit"', (ws_id,)).fetchone()['cnt']
            entries_qty = cursor.execute('SELECT COALESCE(SUM(quantity),0) as s FROM stock_movements sm WHERE sm.workshop_id = ? AND sm.movement_type = "entry"', (ws_id,)).fetchone()['s']
            exits_qty = cursor.execute('SELECT COALESCE(SUM(quantity),0) as s FROM stock_movements sm WHERE sm.workshop_id = ? AND sm.movement_type = "exit"', (ws_id,)).fetchone()['s']

            recent_movements = cursor.execute('''
                SELECT sm.movement_type, sm.quantity, sm.notes, sm.created_at, p.name, u.username
                FROM stock_movements sm
                JOIN products p ON sm.product_id = p.id
                JOIN users u ON sm.user_id = u.id
                WHERE sm.workshop_id = ?
                ORDER BY sm.created_at DESC LIMIT 10
            ''', (ws_id,)).fetchall()

            low_stock_products = cursor.execute('''
                SELECT code, name, quantity FROM products
                WHERE deleted_at IS NULL AND workshop_id = ? AND quantity <= 10
                ORDER BY quantity ASC LIMIT 10
            ''', (ws_id,)).fetchall()

            last_30 = [(datetime.now() - timedelta(days=i)).strftime('%Y-%m-%d') for i in range(29, -1, -1)]
            chart_labels, chart_entries, chart_exits = [], [], []
            for day in last_30:
                chart_labels.append(day[-5:])
                e = cursor.execute("SELECT COALESCE(SUM(quantity),0) as s FROM stock_movements sm WHERE sm.workshop_id = ? AND sm.movement_type = 'entry' AND DATE(sm.created_at) = ?", (ws_id, day)).fetchone()['s']
                chart_entries.append(e)
                x = cursor.execute("SELECT COALESCE(SUM(quantity),0) as s FROM stock_movements sm WHERE sm.workshop_id = ? AND sm.movement_type = 'exit' AND DATE(sm.created_at) = ?", (ws_id, day)).fetchone()['s']
                chart_exits.append(x)

            cat_data = cursor.execute('''
                SELECT category, COUNT(*) as cnt FROM products
                WHERE deleted_at IS NULL AND workshop_id = ? AND category IS NOT NULL AND category != ''
                GROUP BY category ORDER BY cnt DESC LIMIT 10
            ''', (ws_id,)).fetchall()

        return render_template('workshop_dashboard.html', workshop=workshop,
                             total_products=total_products, low_stock_items=low_stock_items,
                             zero_stock_count=zero_stock_count,
                             total_movements=total_movements, total_entries=total_entries,
                             total_exits=total_exits, entries_qty=entries_qty, exits_qty=exits_qty,
                             recent_movements=recent_movements, low_stock_products=low_stock_products,
                             chart_labels=json.dumps(chart_labels),
                             chart_entries=json.dumps(chart_entries),
                             chart_exits=json.dumps(chart_exits),
                             cat_labels=json.dumps([r[0] for r in cat_data]),
                             cat_counts=json.dumps([r[1] for r in cat_data]),
                             translations=TRANSLATIONS[session.get('lang', 'fr')],
                             lang=session.get('lang', 'fr'))

    @app.route('/workshop_comparison')
    @admin_required
    def workshop_comparison():
        with get_db() as conn:
            cursor = conn.cursor()
            workshops = cursor.execute('SELECT * FROM workshops ORDER BY name').fetchall()
            stats = []
            for ws in workshops:
                ws_id = ws['id']
                products_count = cursor.execute('SELECT COUNT(*) as cnt FROM products WHERE deleted_at IS NULL AND workshop_id = ?', (ws_id,)).fetchone()['cnt']
                low_stock = cursor.execute('SELECT COUNT(*) as cnt FROM products WHERE deleted_at IS NULL AND workshop_id = ? AND quantity <= 10', (ws_id,)).fetchone()['cnt']
                movements_count = cursor.execute('SELECT COUNT(*) as cnt FROM stock_movements sm WHERE sm.workshop_id = ?', (ws_id,)).fetchone()['cnt']
                entries_qty = cursor.execute('SELECT COALESCE(SUM(quantity),0) as s FROM stock_movements sm WHERE sm.workshop_id = ? AND sm.movement_type = "entry"', (ws_id,)).fetchone()['s']
                exits_qty = cursor.execute('SELECT COALESCE(SUM(quantity),0) as s FROM stock_movements sm WHERE sm.workshop_id = ? AND sm.movement_type = "exit"', (ws_id,)).fetchone()['s']
                total_qty = cursor.execute('SELECT COALESCE(SUM(quantity),0) as s FROM products WHERE deleted_at IS NULL AND workshop_id = ?', (ws_id,)).fetchone()['s']
                users_count = cursor.execute('SELECT COUNT(*) as cnt FROM users WHERE workshop_id = ?', (ws_id,)).fetchone()['cnt']
                stats.append({
                    'id': ws_id, 'name': ws['name'], 'city': ws['city'], 'active': ws['active'],
                    'products': products_count, 'low_stock': low_stock,
                    'movements': movements_count, 'entries_qty': entries_qty,
                    'exits_qty': exits_qty, 'total_qty': total_qty, 'users': users_count,
                })

        labels = [s['name'] for s in stats]
        data_products = [s['products'] for s in stats]
        data_movements = [s['movements'] for s in stats]
        data_stock = [s['total_qty'] for s in stats]

        return render_template('workshop_comparison.html', stats=stats,
                             chart_labels=json.dumps(labels),
                             chart_products=json.dumps(data_products),
                             chart_movements=json.dumps(data_movements),
                             chart_stock=json.dumps(data_stock),
                             translations=TRANSLATIONS[session.get('lang', 'fr')],
                             lang=session.get('lang', 'fr'))

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