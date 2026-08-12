import logging
from flask import render_template, request, redirect, url_for, session, flash
from db import get_db, query, query_one, execute
from utils import admin_required, get_translation, log_audit
from translations import TRANSLATIONS

logger = logging.getLogger(__name__)


def register_supplier_routes(app):

    @app.route('/suppliers')
    @admin_required
    def suppliers():
        supps = query('SELECT * FROM suppliers ORDER BY name')
        return render_template('suppliers.html', suppliers=supps,
                             translations=TRANSLATIONS[session.get('lang', 'fr')],
                             lang=session.get('lang', 'fr'))

    @app.route('/add_supplier', methods=['POST'])
    @admin_required
    def add_supplier():
        name = request.form.get('name', '').strip()
        if not name:
            flash("Nom du fournisseur requis", 'error')
            return redirect(url_for('suppliers'))
        contact_name = request.form.get('contact_name', '').strip()
        email = request.form.get('email', '').strip()
        phone = request.form.get('phone', '').strip()
        address = request.form.get('address', '').strip()
        notes = request.form.get('notes', '').strip()
        existing = query_one('SELECT id FROM suppliers WHERE name = ?', (name,))
        if existing:
            flash("Ce fournisseur existe déjà", 'error')
            return redirect(url_for('suppliers'))
        execute('INSERT INTO suppliers (name, contact_name, email, phone, address, notes) VALUES (?, ?, ?, ?, ?, ?)',
                (name, contact_name, email, phone, address, notes))
        log_audit('create', 'supplier', None, f"Fournisseur créé: {name}")
        flash("Fournisseur ajouté avec succès", 'success')
        return redirect(url_for('suppliers'))

    @app.route('/edit_supplier/<int:supplier_id>', methods=['POST'])
    @admin_required
    def edit_supplier(supplier_id):
        name = request.form.get('name', '').strip()
        if not name:
            flash("Nom du fournisseur requis", 'error')
            return redirect(url_for('suppliers'))
        existing = query_one('SELECT id FROM suppliers WHERE name = ? AND id != ?', (name, supplier_id))
        if existing:
            flash("Ce fournisseur existe déjà", 'error')
            return redirect(url_for('suppliers'))
        contact_name = request.form.get('contact_name', '').strip()
        email = request.form.get('email', '').strip()
        phone = request.form.get('phone', '').strip()
        address = request.form.get('address', '').strip()
        notes = request.form.get('notes', '').strip()
        execute('''UPDATE suppliers SET name=?, contact_name=?, email=?, phone=?, address=?, notes=?
                WHERE id=?''', (name, contact_name, email, phone, address, notes, supplier_id))
        log_audit('update', 'supplier', supplier_id, f"Fournisseur modifié: {name}")
        flash("Fournisseur modifié avec succès", 'success')
        return redirect(url_for('suppliers'))

    @app.route('/delete_supplier/<int:supplier_id>', methods=['POST'])
    @admin_required
    def delete_supplier(supplier_id):
        s = query_one('SELECT name FROM suppliers WHERE id = ?', (supplier_id,))
        if not s:
            flash("Fournisseur introuvable", 'error')
            return redirect(url_for('suppliers'))
        execute('DELETE FROM suppliers WHERE id = ?', (supplier_id,))
        log_audit('delete', 'supplier', supplier_id, f"Fournisseur supprimé: {s['name']}")
        flash("Fournisseur supprimé avec succès", 'success')
        return redirect(url_for('suppliers'))
