import logging
from flask import render_template, request, redirect, url_for, session, flash
from db import get_db, query, query_one, execute
from utils import admin_required, get_translation, log_audit
from translations import TRANSLATIONS

logger = logging.getLogger(__name__)


def register_category_routes(app):

    @app.route('/categories')
    @admin_required
    def categories():
        cats = query('SELECT * FROM categories ORDER BY name')
        return render_template('categories.html', categories=cats,
                             translations=TRANSLATIONS[session.get('lang', 'fr')],
                             lang=session.get('lang', 'fr'))

    @app.route('/add_category', methods=['POST'])
    @admin_required
    def add_category():
        name = request.form.get('name', '').strip()
        if not name:
            flash("Nom de catégorie requis", 'error')
            return redirect(url_for('categories'))
        existing = query_one('SELECT id FROM categories WHERE name = ?', (name,))
        if existing:
            flash("Cette catégorie existe déjà", 'error')
            return redirect(url_for('categories'))
        execute('INSERT INTO categories (name) VALUES (?)', (name,))
        log_audit('create', 'category', None, f"Catégorie créée: {name}")
        flash("Catégorie ajoutée avec succès", 'success')
        return redirect(url_for('categories'))

    @app.route('/edit_category/<int:category_id>', methods=['POST'])
    @admin_required
    def edit_category(category_id):
        name = request.form.get('name', '').strip()
        if not name:
            flash("Nom de catégorie requis", 'error')
            return redirect(url_for('categories'))
        existing = query_one('SELECT id FROM categories WHERE name = ? AND id != ?', (name, category_id))
        if existing:
            flash("Cette catégorie existe déjà", 'error')
            return redirect(url_for('categories'))
        execute('UPDATE categories SET name = ? WHERE id = ?', (name, category_id))
        log_audit('update', 'category', category_id, f"Catégorie renommée: {name}")
        flash("Catégorie modifiée avec succès", 'success')
        return redirect(url_for('categories'))

    @app.route('/delete_category/<int:category_id>', methods=['POST'])
    @admin_required
    def delete_category(category_id):
        cat = query_one('SELECT name FROM categories WHERE id = ?', (category_id,))
        if not cat:
            flash("Catégorie introuvable", 'error')
            return redirect(url_for('categories'))
        execute('DELETE FROM categories WHERE id = ?', (category_id,))
        log_audit('delete', 'category', category_id, f"Catégorie supprimée: {cat['name']}")
        flash("Catégorie supprimée avec succès", 'success')
        return redirect(url_for('categories'))
