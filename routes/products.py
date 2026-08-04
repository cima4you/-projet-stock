import os
import logging
import xlsxwriter
import pandas as pd
import numpy as np
from io import BytesIO
from datetime import datetime, timedelta
from flask import render_template, request, redirect, url_for, session, flash, Response
from werkzeug.utils import secure_filename
from db import get_db, query, query_one, execute
from utils import login_required, admin_required, allowed_excel_file, get_translation, log_audit, workshop_filter
from notifications import send_product_deletion_notification, send_product_addition_notification
from translations import TRANSLATIONS
from config import UPLOAD_FOLDER

logger = logging.getLogger(__name__)


def register_product_routes(app):

    @app.route('/products')
    @login_required
    def products():
        page = request.args.get('page', 1, type=int)
        per_page = 50
        offset = (page - 1) * per_page

        with get_db() as conn:
            cursor = conn.cursor()
            category_filter = request.args.get('category', '')
            search_query = request.args.get('search', '')
            type_achat_filter = request.args.get('type_achat', '')
            supplier_name_filter = request.args.get('supplier_name', '')
            storage_zone_filter = request.args.get('storage_zone', '')
            brand_filter = request.args.get('brand', '')
            date_from = request.args.get('date_from', '')
            date_to = request.args.get('date_to', '')
            filter_workshop = request.args.get('workshop', '')
            try:
                fws = int(filter_workshop) if filter_workshop else None
            except ValueError:
                fws = None

            where = ' WHERE deleted_at IS NULL'
            params = []
            role = session.get('role')
            if role in ('admin', 'principal_admin') and fws:
                ws_clause = ' AND workshop_id = ?'
                ws_params = [fws]
            else:
                ws_clause, ws_params = workshop_filter()
                if role not in ('admin', 'principal_admin'):
                    fws = None
            where += ws_clause
            params.extend(ws_params)
            if category_filter:
                where += ' AND category LIKE ?'
                params.append(f'%{category_filter}%')
            if search_query:
                where += ' AND (code LIKE ? OR name LIKE ? OR brand LIKE ? OR supplier_name LIKE ? OR notes LIKE ?)'
                params.extend([f'%{search_query}%'] * 5)
            if type_achat_filter:
                where += ' AND type_achat = ?'
                params.append(type_achat_filter)
            if supplier_name_filter:
                where += ' AND supplier_name LIKE ?'
                params.append(f'%{supplier_name_filter}%')
            if storage_zone_filter:
                where += ' AND storage_zone LIKE ?'
                params.append(f'%{storage_zone_filter}%')
            if brand_filter:
                where += ' AND brand LIKE ?'
                params.append(f'%{brand_filter}%')
            if date_from:
                where += ' AND DATE(created_at) >= ?'
                params.append(date_from)
            if date_to:
                where += ' AND DATE(created_at) <= ?'
                params.append(date_to)

            cursor.execute('SELECT COUNT(*) FROM products' + where, params)
            total = cursor.fetchone()[0]
            total_pages = max(1, (total + per_page - 1) // per_page)

            q = 'SELECT * FROM products' + where + ' ORDER BY created_at DESC LIMIT ? OFFSET ?'
            cursor.execute(q, params + [per_page, offset])
            products_list = cursor.fetchall()

            cursor.execute('SELECT DISTINCT category FROM products WHERE category IS NOT NULL AND category != "" AND deleted_at IS NULL' + ws_clause, ws_params)
            categories = [row[0] for row in cursor.fetchall()]

        all_cats = query('SELECT name FROM categories ORDER BY name')
        all_supps = query('SELECT name FROM suppliers ORDER BY name')
        workshops = query('SELECT id, name, city FROM workshops WHERE active = 1 ORDER BY name')
        expiring_soon_date = (datetime.now() + timedelta(days=30)).strftime('%Y-%m-%d')

        return render_template('products.html', products=products_list, categories=categories,
                             all_categories=[r['name'] for r in all_cats],
                             all_suppliers=[r['name'] for r in all_supps],
                             expiring_soon=expiring_soon_date,
                             category_filter=category_filter, search_query=search_query,
                             type_achat_filter=type_achat_filter, supplier_name_filter=supplier_name_filter,
                             storage_zone_filter=storage_zone_filter, brand_filter=brand_filter,
                             date_from=date_from, date_to=date_to,
                             filter_workshop=fws, workshops=workshops,
                             page=page, total_pages=total_pages, total=total,
                             today=datetime.now().date().strftime('%Y-%m-%d'),
                             translations=TRANSLATIONS[session.get('lang', 'fr')],
                             lang=session.get('lang', 'fr'))

    @app.route('/add_product', methods=['GET', 'POST'])
    @login_required
    def add_product():
        if request.method == 'POST':
            try:
                code = request.form['code'].strip()
                name = request.form['name'].strip()
                category = request.form.get('category', '').strip()
                unit = request.form.get('unit', '').strip()
                quantity = int(request.form.get('quantity', 0))
                brand = request.form.get('brand', '').strip()
                condition_status = request.form.get('condition_status', '').strip()
                chanter = request.form.get('chanter', '').strip()
                storage_zone = request.form.get('storage_zone', '').strip()
                notes = request.form.get('notes', '').strip()
                supplier_name = request.form.get('supplier_name', '').strip()
                bc_number = request.form.get('bc_number', '').strip()
                bl_number = request.form.get('bl_number', '').strip()
                n_facture = request.form.get('n_facture', '').strip()
                type_achat = request.form.get('type_achat', '').strip()
                expiration_date = request.form.get('expiration_date', None) or None
                min_quantity = int(request.form.get('min_quantity', 0))

                with get_db() as conn:
                    cursor = conn.cursor()
                    ws_id = session.get('workshop_id')
                    cursor.execute('SELECT id FROM products WHERE code = ? AND (workshop_id = ? OR (workshop_id IS NULL AND ? IS NULL))',
                                  (code, ws_id, ws_id))
                    if cursor.fetchone():
                        flash(get_translation('product_code_already_exists'), 'error')
                        return render_template('add_product.html',
                                             translations=TRANSLATIONS[session.get('lang', 'fr')],
                                             lang=session.get('lang', 'fr'))
                    cursor.execute('''
                        INSERT INTO products (code, name, category, unit, quantity, brand, condition_status,
                                            chanter, storage_zone, notes, supplier_name, bc_number, bl_number,
                                            n_facture, type_achat, expiration_date, min_quantity, workshop_id,
                                            created_by)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (code, name, category, unit, quantity, brand, condition_status,
                          chanter, storage_zone, notes, supplier_name, bc_number, bl_number,
                          n_facture, type_achat, expiration_date, min_quantity, ws_id,
                          session.get('user_id')))
                    product_id = cursor.lastrowid
                    log_audit('create', 'product', product_id, f"Création du produit {code} - {name}")

                    if quantity > 0:
                        cursor.execute('''
                            INSERT INTO stock_movements (product_id, movement_type, quantity, notes, user_id,
                                                        supplier_name, bc_number, bl_number, n_facture, type_achat)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        ''', (product_id, 'entry', quantity, 'Ajout initial du produit', session['user_id'],
                              supplier_name, bc_number, bl_number, n_facture, type_achat))
                        send_product_addition_notification(
                            {'id': product_id, 'code': code, 'name': name, 'quantity': quantity, 'type_achat': type_achat,
                             'supplier_name': supplier_name, 'bc_number': bc_number, 'bl_number': bl_number,
                             'n_facture': n_facture},
                            'entry', session['username'], session.get('lang', 'fr'),
                            workshop_id=session.get('workshop_id'))

                flash(get_translation('product_added_successfully'), 'success')
                return redirect(url_for('products'))
            except Exception as e:
                logger.error(f"Error adding product: {e}")
                flash(f"Erreur lors de l'ajout du produit: {str(e)}", 'error')

        all_cats = query('SELECT name FROM categories ORDER BY name')
        all_supps = query('SELECT name FROM suppliers ORDER BY name')
        return render_template('add_product.html',
                             all_categories=[r['name'] for r in all_cats],
                             all_suppliers=[r['name'] for r in all_supps],
                             translations=TRANSLATIONS[session.get('lang', 'fr')],
                             lang=session.get('lang', 'fr'))

    @app.route('/edit_product/<int:product_id>', methods=['GET', 'POST'])
    @admin_required
    def edit_product(product_id):
        with get_db() as conn:
            cursor = conn.cursor()
            if request.method == 'POST':
                try:
                    code = request.form['code'].strip()
                    name = request.form['name'].strip()
                    category = request.form.get('category', '').strip()
                    unit = request.form.get('unit', '').strip()
                    brand = request.form.get('brand', '').strip()
                    condition_status = request.form.get('condition_status', '').strip()
                    chanter = request.form.get('chanter', '').strip()
                    storage_zone = request.form.get('storage_zone', '').strip()
                    notes = request.form.get('notes', '').strip()
                    supplier_name = request.form.get('supplier_name', '').strip()
                    bc_number = request.form.get('bc_number', '').strip()
                    bl_number = request.form.get('bl_number', '').strip()
                    n_facture = request.form.get('n_facture', '').strip()
                    type_achat = request.form.get('type_achat', '').strip()
                    expiration_date = request.form.get('expiration_date', None) or None
                    min_quantity = int(request.form.get('min_quantity', 0))

                    ws_id = session.get('workshop_id')
                    cursor.execute('SELECT id FROM products WHERE code = ? AND id != ? AND (workshop_id = ? OR (workshop_id IS NULL AND ? IS NULL))',
                                  (code, product_id, ws_id, ws_id))
                    if cursor.fetchone():
                        flash(get_translation('product_code_already_exists'), 'error')
                        return redirect(url_for('edit_product', product_id=product_id))

                    cursor.execute('''
                        UPDATE products SET code=?, name=?, category=?, unit=?, brand=?,
                                          condition_status=?, chanter=?, storage_zone=?, notes=?,
                                          supplier_name=?, bc_number=?, bl_number=?, n_facture=?,
                                          type_achat=?, expiration_date=?, min_quantity=?,
                                          updated_at=CURRENT_TIMESTAMP
                        WHERE id=?
                    ''', (code, name, category, unit, brand, condition_status, chanter, storage_zone,
                          notes, supplier_name, bc_number, bl_number, n_facture, type_achat,
                          expiration_date, min_quantity, product_id))
                    log_audit('update', 'product', product_id, f"Mise à jour du produit {code} - {name}")
                    flash(get_translation('product_updated_successfully'), 'success')
                    return redirect(url_for('products'))
                except Exception as e:
                    logger.error(f"Error updating product: {e}")
                    flash(f"Erreur lors de la mise à jour: {str(e)}", 'error')

            cursor.execute('SELECT * FROM products WHERE id = ?', (product_id,))
            product = cursor.fetchone()
            if not product:
                flash(get_translation('product_not_found'), 'error')
                return redirect(url_for('products'))

        all_cats = query('SELECT name FROM categories ORDER BY name')
        all_supps = query('SELECT name FROM suppliers ORDER BY name')
        return render_template('edit_product.html', product=product,
                             all_categories=[r['name'] for r in all_cats],
                             all_suppliers=[r['name'] for r in all_supps],
                             translations=TRANSLATIONS[session.get('lang', 'fr')],
                             lang=session.get('lang', 'fr'))

    @app.route('/delete_product/<int:product_id>')
    @admin_required
    def delete_product(product_id):
        try:
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT code, name FROM products WHERE id = ?', (product_id,))
                product = cursor.fetchone()
                if not product:
                    flash(get_translation('product_not_found'), 'error')
                    return redirect(url_for('products'))
                product_info = {'id': product_id, 'code': product['code'], 'name': product['name']}
                log_audit('delete', 'product', product_id, f"Archive du produit {product['code']} - {product['name']}")
                cursor.execute('UPDATE products SET deleted_at = CURRENT_TIMESTAMP WHERE id = ?', (product_id,))

            send_product_deletion_notification(product_info, deleted_by_user=session['username'],
                                                lang=session.get('lang', 'fr'),
                                                workshop_id=session.get('workshop_id'))
            flash("Produit archivé avec succès", 'success')
        except Exception as e:
            logger.error(f"Error archiving product: {e}")
            flash(f"Erreur lors de l'archivage: {str(e)}", 'error')
        return redirect(url_for('products'))

    @app.route('/restore_product/<int:product_id>')
    @admin_required
    def restore_product(product_id):
        try:
            execute('UPDATE products SET deleted_at = NULL WHERE id = ?', (product_id,))
            log_audit('restore', 'product', product_id, f"Produit #{product_id} restauré")
            flash("Produit restauré avec succès", 'success')
        except Exception as e:
            flash(f"Erreur: {str(e)}", 'error')
        return redirect(url_for('archived_products'))

    @app.route('/archived_products')
    @admin_required
    def archived_products():
        page = request.args.get('page', 1, type=int)
        per_page = 50
        offset = (page - 1) * per_page

        with get_db() as conn:
            cursor = conn.cursor()
            ws_clause, ws_params = workshop_filter()
            cursor.execute('SELECT COUNT(*) FROM products WHERE deleted_at IS NOT NULL' + ws_clause, ws_params)
            total = cursor.fetchone()[0]
            total_pages = max(1, (total + per_page - 1) // per_page)
            cursor.execute('SELECT * FROM products WHERE deleted_at IS NOT NULL' + ws_clause + ' ORDER BY deleted_at DESC LIMIT ? OFFSET ?',
                          ws_params + [per_page, offset])
            prods = cursor.fetchall()

        return render_template('archived_products.html', products=prods,
                             page=page, total_pages=total_pages, total=total,
                             translations=TRANSLATIONS[session.get('lang', 'fr')],
                             lang=session.get('lang', 'fr'))

    @app.route('/import_products', methods=['GET', 'POST'])
    @login_required
    def import_products():
        if request.method == 'POST':
            if 'file' not in request.files:
                flash(get_translation('no_file_selected'), 'error')
                return redirect(request.url)
            file = request.files['file']
            if file.filename == '':
                flash(get_translation('no_file_selected'), 'error')
                return redirect(request.url)
            if file and allowed_excel_file(file.filename):
                try:
                    filename = secure_filename(file.filename)
                    filepath = os.path.join(UPLOAD_FOLDER, filename)
                    file.save(filepath)
                    success, message, imported_count, errors = _import_from_excel(filepath, session['user_id'], session.get('workshop_id'))
                    os.remove(filepath)
                    if success:
                        flash(f"{message}. {get_translation('products_imported_successfully')}", 'success')
                        if errors:
                            session['import_errors'] = errors
                            return redirect(url_for('import_errors'))
                    else:
                        flash(f"{get_translation('error_importing_products')}: {message}", 'error')
                except Exception as e:
                    logger.error(f"Import error: {e}")
                    flash(f"{get_translation('error_importing_products')}: {str(e)}", 'error')
            else:
                flash(get_translation('invalid_file_type'), 'error')
        return render_template('import_products.html',
                             translations=TRANSLATIONS[session.get('lang', 'fr')],
                             lang=session.get('lang', 'fr'))

    @app.route('/import_errors')
    @login_required
    def import_errors():
        errors = session.pop('import_errors', [])
        return render_template('import_errors.html', errors=errors,
                             translations=TRANSLATIONS[session.get('lang', 'fr')],
                             lang=session.get('lang', 'fr'))

    @app.route('/product_reports')
    @login_required
    def product_reports():
        try:
            with get_db() as conn:
                cursor = conn.cursor()
                category_filter = request.args.get('category', '')
                search_query = request.args.get('search', '')
                q = 'SELECT p.*, u.username as created_by_username FROM products p LEFT JOIN users u ON p.created_by = u.id WHERE p.deleted_at IS NULL'
                params = []
                ws_clause, ws_params = workshop_filter('p')
                q += ws_clause
                params.extend(ws_params)
                if category_filter:
                    q += ' AND p.category LIKE ?'
                    params.append(f'%{category_filter}%')
                if search_query:
                    q += ' AND (p.code LIKE ? OR p.name LIKE ? OR p.brand LIKE ?)'
                    params.extend([f'%{search_query}%'] * 3)
                q += ' ORDER BY p.name'
                cursor.execute(q, params)
                products_data = cursor.fetchall()
                cursor.execute('SELECT DISTINCT p.category FROM products p WHERE p.category IS NOT NULL AND p.category != "" AND p.deleted_at IS NULL')
                categories = [row[0] for row in cursor.fetchall()]
            return render_template('product_reports.html', products=products_data, categories=categories,
                                 category_filter=category_filter, search_query=search_query,
                                 today=datetime.now().date().strftime('%Y-%m-%d'),
                                 translations=TRANSLATIONS[session.get('lang', 'fr')],
                                 lang=session.get('lang', 'fr'))
        except Exception as e:
            logger.error(f"Error loading product reports: {e}", exc_info=True)
            flash(f"Erreur lors du chargement du rapport: {str(e)}", 'error')
            return redirect(url_for('reports'))

    @app.route('/export_products_excel')
    @login_required
    def export_products_excel():
        try:
            category_filter = request.args.get('category', '')
            search_query = request.args.get('search', '')
            export_cols = [
                'p.id', 'p.code', 'p.name', 'p.category', 'p.unit', 'p.quantity',
                'p.brand', 'p.condition_status', 'p.chanter', 'p.storage_zone',
                'p.notes', 'p.supplier_name', 'p.bc_number', 'p.bl_number',
                'p.n_facture', 'p.type_achat', 'p.expiration_date',
                'p.min_quantity', 'p.workshop_id', 'p.created_at', 'p.updated_at',
                'p.created_by', 'p.deleted_at', 'p.image_path',
                'u.username as created_by_username',
            ]
            q = f'SELECT {", ".join(export_cols)} FROM products p LEFT JOIN users u ON p.created_by = u.id WHERE p.deleted_at IS NULL'
            params = []
            ws_clause, ws_params = workshop_filter('p')
            q += ws_clause
            params.extend(ws_params)
            if category_filter:
                q += ' AND p.category LIKE ?'
                params.append(f'%{category_filter}%')
            if search_query:
                q += ' AND (p.code LIKE ? OR p.name LIKE ? OR p.brand LIKE ?)'
                params.extend([f'%{search_query}%'] * 3)
            q += ' ORDER BY p.name'

            products_data = query(q, tuple(params))

            headers = [
                'ID', 'Code Produit', 'Nom du Produit', 'Catégorie', 'Unité', 'Quantité',
                'Marque', 'État', 'Chantier', 'Zone de Stockage',
                'Notes', 'Nom Fournisseur', 'Numéro BC', 'Numéro BL',
                'Numéro Facture', "Type d'Achat", "Date d'Expiration",
                'Qté Min', 'Atelier', 'Créé le', 'Mis à jour le',
                'ID Créateur', 'Supprimé le', 'Image', 'Créé par',
            ]


            output = BytesIO()
            workbook = xlsxwriter.Workbook(output)
            worksheet = workbook.add_worksheet('Produits')
            header_fmt = workbook.add_format({'bold': True, 'bg_color': '#D3D3D3', 'font_size': 12, 'align': 'center', 'border': 1})
            data_fmt = workbook.add_format({'font_size': 11, 'border': 1})
            for col, header in enumerate(headers):
                worksheet.write(0, col, header, header_fmt)
            for r_idx, product in enumerate(products_data, 1):
                for c_idx, value in enumerate(product):
                    if isinstance(value, str) and len(value) == 10 and '-' in value:
                        try:
                            date_obj = datetime.strptime(value, '%Y-%m-%d')
                            worksheet.write_datetime(r_idx, c_idx, date_obj, data_fmt)
                        except ValueError:
                            worksheet.write(r_idx, c_idx, value, data_fmt)
                    else:
                        worksheet.write(r_idx, c_idx, value, data_fmt)
            for col in range(len(headers)):
                worksheet.set_column(col, col, 18)
            workbook.close()
            output.seek(0)

            return Response(
                output.getvalue(),
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                headers={
                    'Content-Disposition': f'attachment; filename=rapport_produits_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx',
                    'Cache-Control': 'no-store, no-cache, must-revalidate, max-age=0',
                    'Pragma': 'no-cache',
                }
            )
        except Exception as e:
            logger.error(f"Error exporting products: {e}")
            flash(f"Erreur lors de l'export: {str(e)}", 'error')
            return redirect(url_for('product_reports'))

def _import_from_excel(file_path: str, user_id: int, workshop_id=None):
    df = pd.read_excel(file_path)
    column_mapping = {
        'كود المنتج': 'code', 'Product Code': 'code', 'code': 'code', 'Code Produit': 'code',
        'اسم المنتج': 'name', 'Product Name': 'name', 'name': 'name', 'Nom du Produit': 'name',
        'الفئة': 'category', 'Category': 'category', 'category': 'category', 'Catégorie': 'category',
        'الوحدة': 'unit', 'Unit': 'unit', 'unit': 'unit', 'Unité': 'unit',
        'الكمية': 'quantity', 'Quantity': 'quantity', 'quantity': 'quantity', 'Quantité': 'quantity',
        'الماركة': 'brand', 'Brand': 'brand', 'brand': 'brand', 'Marque': 'brand',
        'الحالة': 'condition_status', 'Condition': 'condition_status', 'condition_status': 'condition_status', 'État': 'condition_status',
        'الورشة': 'chanter', 'Workshop': 'chanter', 'chanter': 'chanter', 'Chantier': 'chanter',
        'منطقة التخزين': 'storage_zone', 'Storage Zone': 'storage_zone', 'storage_zone': 'storage_zone', 'Zone de Stockage': 'storage_zone',
        'ملاحظات': 'notes', 'Notes': 'notes', 'notes': 'notes',
        'اسم المورد': 'supplier_name', 'Supplier Name': 'supplier_name', 'supplier_name': 'supplier_name', 'Nom Fournisseur': 'supplier_name',
        'رقم أمر الشراء': 'bc_number', 'BC Number': 'bc_number', 'bc_number': 'bc_number', 'Numéro BC': 'bc_number',
        'رقم بوليصة الشحن': 'bl_number', 'BL Number': 'bl_number', 'bl_number': 'bl_number', 'Numéro BL': 'bl_number',
        'رقم الفاتورة': 'n_facture', 'Invoice Number': 'n_facture', 'n_facture': 'n_facture', 'Numéro Facture': 'n_facture',
        'نوع الشراء': 'type_achat', 'Purchase Type': 'type_achat', 'type_achat': 'type_achat', "Type d'Achat": 'type_achat',
        'تاريخ انتهاء الصلاحية': 'expiration_date', 'Expiration Date': 'expiration_date', 'expiration_date': 'expiration_date', "Date d'Expiration": 'expiration_date'
    }
    df = df.rename(columns={col: column_mapping[col] for col in df.columns if col in column_mapping})

    if 'code' not in df.columns or 'name' not in df.columns:
        return False, "Missing required columns: code, name", 0, []

    with get_db() as conn:
        cursor = conn.cursor()
        imported_count = 0
        errors = []
        for index, row in df.iterrows():
            try:
                cursor.execute('SELECT id FROM products WHERE code = ? AND deleted_at IS NULL', (row['code'],))
                if cursor.fetchone():
                    errors.append(f"Row {index + 1}: Product with code '{row['code']}' already exists")
                    continue

                exp_date = row.get('expiration_date', None)
                if pd.notna(exp_date):
                    if isinstance(exp_date, str):
                        for fmt in ['%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y', '%d-%m-%Y']:
                            try:
                                exp_date = datetime.strptime(exp_date, fmt).strftime('%Y-%m-%d')
                                break
                            except ValueError:
                                continue
                    elif hasattr(exp_date, 'strftime'):
                        exp_date = exp_date.strftime('%Y-%m-%d')
                else:
                    exp_date = None

                ws_id = session.get('workshop_id') if hasattr(session, 'get') else None
                cursor.execute('''
                    INSERT INTO products (code, name, category, unit, quantity, brand, condition_status,
                                        chanter, storage_zone, notes, supplier_name, bc_number, bl_number,
                                        n_facture, type_achat, expiration_date, min_quantity, workshop_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    row['code'], row['name'], row.get('category', ''), row.get('unit', ''),
                    int(row.get('quantity', 0)) if pd.notna(row.get('quantity', 0)) else 0,
                    row.get('brand', ''), row.get('condition_status', ''), row.get('chanter', ''),
                    row.get('storage_zone', ''), row.get('notes', ''), row.get('supplier_name', ''),
                    row.get('bc_number', ''), row.get('bl_number', ''), row.get('n_facture', ''),
                    row.get('type_achat', ''), exp_date, 0, ws_id
                ))
                product_id = cursor.lastrowid

                qty = int(row.get('quantity', 0)) if pd.notna(row.get('quantity', 0)) else 0
                if qty > 0:
                    cursor.execute('''
                        INSERT INTO stock_movements (product_id, movement_type, quantity, notes, user_id,
                                                    supplier_name, bc_number, bl_number, n_facture, type_achat)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (product_id, 'entry', qty, 'Import automatique from Excel', user_id,
                          row.get('supplier_name', ''), row.get('bc_number', ''), row.get('bl_number', ''),
                          row.get('n_facture', ''), row.get('type_achat', '')))
                    send_product_addition_notification(
                        {'id': product_id, 'code': row['code'], 'name': row['name'],
                         'quantity': qty, 'type_achat': row.get('type_achat', ''),
                         'supplier_name': row.get('supplier_name', ''), 'bc_number': row.get('bc_number', ''),
                         'bl_number': row.get('bl_number', ''), 'n_facture': row.get('n_facture', '')},
                        'entry', 'Système (Import Excel)', 'fr',
                        workshop_id=workshop_id)

                imported_count += 1
            except Exception as e:
                errors.append(f"Row {index + 1}: {str(e)}")
                continue

    return True, f"Successfully imported {imported_count} products", imported_count, errors



