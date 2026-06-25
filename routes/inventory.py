import logging
from datetime import datetime
from flask import render_template, request, redirect, url_for, session, flash, jsonify
from db import get_db, query, query_one, execute
from utils import login_required, admin_required, get_translation, log_audit, workshop_filter
from translations import TRANSLATIONS

logger = logging.getLogger(__name__)


def register_inventory_routes(app):

    @app.route('/inventory')
    @admin_required
    def inventory():
        ws_clause, ws_params = workshop_filter('p')
        counts = query('''
            SELECT ic.*, p.code, p.name
            FROM inventory_counts ic
            JOIN products p ON ic.product_id = p.id
            WHERE 1=1''' + ws_clause + '''
            ORDER BY ic.counted_at DESC LIMIT 100
        ''', tuple(ws_params)) or []
        products = query('SELECT id, code, name, quantity FROM products WHERE deleted_at IS NULL' + ws_clause.replace('p.', '') + ' ORDER BY name', tuple(ws_params))
        return render_template('inventory.html', counts=counts, products=products,
                             translations=TRANSLATIONS[session.get('lang', 'fr')],
                             lang=session.get('lang', 'fr'))

    @app.route('/inventory/count', methods=['POST'])
    @admin_required
    def inventory_count():
        product_id = int(request.form['product_id'])
        actual_qty = int(request.form['actual_qty'])
        notes = request.form.get('notes', '').strip()
        product = query_one('SELECT id, quantity, code, name FROM products WHERE id = ?', (product_id,))
        if not product:
            flash("Produit introuvable", 'error')
            return redirect(url_for('inventory'))
        diff = actual_qty - product['quantity']
        execute('''
            INSERT INTO inventory_counts (product_id, theoretical_qty, actual_qty, difference, notes, counted_by)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (product_id, product['quantity'], actual_qty, diff, notes, session['username']))
        execute('UPDATE products SET quantity = ? WHERE id = ?', (actual_qty, product_id))
        log_audit('inventory', 'product', product_id,
                  f"Inventaire: {product['code']} ({product['name']}) théorique={product['quantity']} réel={actual_qty} écart={diff}")
        flash(f"Inventaire enregistré pour {product['code']} - {product['name']}. Écart: {diff:+d}", 'success')
        return redirect(url_for('inventory'))

    @app.route('/api/product_info/<int:product_id>')
    @login_required
    def product_info(product_id):
        p = query_one('SELECT id, code, name, quantity, min_quantity, category, supplier_name, storage_zone FROM products WHERE id = ?', (product_id,))
        if not p:
            return jsonify({'error': 'not found'}), 404
        return jsonify({
            'id': p['id'], 'code': p['code'], 'name': p['name'],
            'quantity': p['quantity'], 'min_quantity': p['min_quantity'],
            'category': p['category'], 'supplier_name': p['supplier_name'],
            'storage_zone': p['storage_zone'],
        })
