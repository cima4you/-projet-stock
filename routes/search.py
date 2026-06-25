import logging
from flask import jsonify, request, session
from db import query
from utils import login_required, workshop_filter

logger = logging.getLogger(__name__)


def register_search_routes(app):

    @app.route('/api/search_products')
    @login_required
    def search_products():
        q = request.args.get('q', '').strip()
        if len(q) < 1:
            return jsonify([])
        ws_clause, ws_params = workshop_filter()
        all_params = tuple(ws_params) + (f'%{q}%', f'%{q}%', f'%{q}%', f'%{q}%')
        rows = query('''
            SELECT id, code, name, quantity, min_quantity, category, supplier_name, storage_zone
            FROM products
            WHERE deleted_at IS NULL''' + ws_clause + '''
              AND (code LIKE ? OR name LIKE ? OR supplier_name LIKE ? OR category LIKE ?)
            ORDER BY name LIMIT 20
        ''', all_params)
        return jsonify([{
            'id': r['id'],
            'code': r['code'],
            'name': r['name'],
            'quantity': r['quantity'],
            'min_quantity': r['min_quantity'],
            'category': r['category'],
            'supplier_name': r['supplier_name'],
            'storage_zone': r['storage_zone'],
        } for r in rows])
