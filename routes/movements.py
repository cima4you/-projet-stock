import json
import logging
import xlsxwriter
from io import BytesIO
from datetime import datetime
from flask import render_template, request, redirect, url_for, session, flash, Response
from db import get_db, query, query_one
from utils import login_required, admin_required, get_translation, excel_serial_to_datetime, log_audit, workshop_filter, build_change_details
from notifications import send_product_addition_notification, send_product_exit_notification
from translations import TRANSLATIONS

logger = logging.getLogger(__name__)


def register_movement_routes(app):

    @app.route('/movements')
    @login_required
    def movements():
        page = request.args.get('page', 1, type=int)
        per_page = 50
        offset = (page - 1) * per_page

        with get_db() as conn:
            cursor = conn.cursor()
            type_filter = request.args.get('type', '')
            search_query = request.args.get('search', '')
            supplier_name_filter = request.args.get('supplier_name', '')
            type_achat_filter = request.args.get('type_achat', '')
            chantier_filter = request.args.get('chantier', '')
            date_from = request.args.get('date_from', '')
            date_to = request.args.get('date_to', '')
            filter_workshop = request.args.get('workshop', '')
            try:
                fws = int(filter_workshop) if filter_workshop else None
            except ValueError:
                fws = None

            where = ' WHERE 1=1'
            params = []
            role = session.get('role')
            if role in ('admin', 'principal_admin') and fws:
                ws_clause = ' AND sm.workshop_id = ?'
                ws_params = [fws]
            else:
                ws_clause, ws_params = workshop_filter('sm')
                if role not in ('admin', 'principal_admin'):
                    fws = None
            where += ws_clause
            params.extend(ws_params)
            if type_filter:
                where += ' AND sm.movement_type = ?'
                params.append(type_filter)
            if search_query:
                where += ' AND (p.code LIKE ? OR p.name LIKE ? OR sm.notes LIKE ? OR sm.chantier_exp_recep LIKE ? OR sm.nom_donneur_ordre LIKE ? OR sm.nom_magasinier LIKE ? OR sm.nom_chauffeur LIKE ? OR sm.matricule LIKE ?)'
                params.extend([f'%{search_query}%'] * 8)
            if supplier_name_filter:
                where += ' AND sm.supplier_name LIKE ?'
                params.append(f'%{supplier_name_filter}%')
            if type_achat_filter:
                where += ' AND sm.type_achat = ?'
                params.append(type_achat_filter)
            if chantier_filter:
                where += ' AND sm.chantier_exp_recep LIKE ?'
                params.append(f'%{chantier_filter}%')
            if date_from:
                where += ' AND DATE(sm.created_at) >= ?'
                params.append(date_from)
            if date_to:
                where += ' AND DATE(sm.created_at) <= ?'
                params.append(date_to)

            count_q = '''
                SELECT COUNT(*) FROM stock_movements sm
                JOIN products p ON sm.product_id = p.id
                JOIN users u ON sm.user_id = u.id
            ''' + where
            cursor.execute(count_q, params)
            total = cursor.fetchone()[0]
            total_pages = max(1, (total + per_page - 1) // per_page)

            q = '''
                SELECT sm.id, sm.movement_type, sm.quantity, sm.notes, sm.created_at,
                       p.code, p.name, u.username, sm.supplier_name, sm.bc_number,
                       sm.bl_number, sm.n_facture, sm.type_achat,
                       sm.chantier_exp_recep, sm.nom_donneur_ordre, sm.nom_magasinier,
                       sm.nom_chauffeur, sm.matricule
                FROM stock_movements sm
                JOIN products p ON sm.product_id = p.id
                JOIN users u ON sm.user_id = u.id
            ''' + where + ' ORDER BY sm.created_at DESC LIMIT ? OFFSET ?'
            cursor.execute(q, params + [per_page, offset])
            movements_list = cursor.fetchall()

        workshops = query('SELECT id, name, city FROM workshops WHERE active = 1 ORDER BY name')
        return render_template('movements.html', movements=movements_list,
                             type_filter=type_filter, search_query=search_query,
                             supplier_name_filter=supplier_name_filter,
                             type_achat_filter=type_achat_filter,
                             chantier_filter=chantier_filter,
                             date_from=date_from, date_to=date_to,
                             filter_workshop=fws, workshops=workshops,
                             page=page, total_pages=total_pages, total=total,
                             translations=TRANSLATIONS[session.get('lang', 'fr')],
                             lang=session.get('lang', 'fr'))

    @app.route('/product_history/<int:product_id>')
    @login_required
    def product_history(product_id):
        product = query_one('SELECT * FROM products WHERE id = ?', (product_id,))
        if not product:
            flash("Produit introuvable", 'error')
            return redirect(url_for('products'))
        movements_list = query('''
            SELECT sm.id, sm.movement_type, sm.quantity, sm.notes, sm.created_at,
                   p.code, p.name, u.username, sm.supplier_name, sm.bc_number,
                   sm.bl_number, sm.n_facture, sm.type_achat,
                   sm.chantier_exp_recep, sm.nom_donneur_ordre, sm.nom_magasinier,
                   sm.nom_chauffeur, sm.matricule, p.id as pid
            FROM stock_movements sm
            JOIN products p ON sm.product_id = p.id
            JOIN users u ON sm.user_id = u.id
            WHERE sm.product_id = ?
            ORDER BY sm.created_at DESC
        ''', (product_id,))

        # Stock evolution chart data
        movements_asc = query('''
            SELECT movement_type, quantity, created_at
            FROM stock_movements
            WHERE product_id = ?
            ORDER BY created_at ASC
        ''', (product_id,))
        net_change = 0
        for m in movements_asc:
            net_change += m[1] if m[0] == 'entry' else -m[1]
        initial_stock = (product[5] or 0) - net_change
        stock_labels = []
        stock_data = []
        running = initial_stock
        for m in movements_asc:
            running += m[1] if m[0] == 'entry' else -m[1]
            date_str = m[2][:10] if m[2] else ''
            stock_labels.append(date_str)
            stock_data.append(running)
        min_qty = product[18] or 0

        return render_template('product_history.html', product=product, movements=movements_list,
                             stock_labels=json.dumps(stock_labels),
                             stock_data=json.dumps(stock_data),
                             min_qty=min_qty,
                             translations=TRANSLATIONS[session.get('lang', 'fr')],
                             lang=session.get('lang', 'fr'))

    @app.route('/add_movement', methods=['GET', 'POST'])
    @login_required
    def add_movement():
        if request.method == 'POST':
            try:
                product_id = int(request.form['product_id'])
                movement_type = request.form['movement_type']
                quantity = int(request.form['quantity'])
                notes = request.form.get('notes', '').strip()
                supplier_name = request.form.get('supplier_name', '').strip()
                bc_number = request.form.get('bc_number', '').strip()
                bl_number = request.form.get('bl_number', '').strip()
                n_facture = request.form.get('n_facture', '').strip()
                type_achat = request.form.get('type_achat', '').strip()
                chantier_exp_recep = request.form.get('chantier_exp_recep', '').strip()
                nom_donneur_ordre = request.form.get('nom_donneur_ordre', '').strip()
                nom_magasinier = request.form.get('nom_magasinier', '').strip()
                nom_chauffeur = request.form.get('nom_chauffeur', '').strip()
                matricule = request.form.get('matricule', '').strip()

                with get_db() as conn:
                    cursor = conn.cursor()
                    cursor.execute('SELECT quantity FROM products WHERE id = ?', (product_id,))
                    row = cursor.fetchone()
                    if not row:
                        flash("Produit introuvable", 'error')
                        return redirect(url_for('add_movement'))
                    current_quantity = row['quantity']

                    if movement_type == 'exit' and quantity > current_quantity:
                        flash(get_translation('insufficient_stock'), 'error')
                        return redirect(url_for('add_movement'))

                    ws_id = session.get('workshop_id')
                    cursor.execute('''
                        INSERT INTO stock_movements (
                            product_id, movement_type, quantity, notes, user_id,
                            supplier_name, bc_number, bl_number, n_facture, type_achat,
                            chantier_exp_recep, nom_donneur_ordre, nom_magasinier, nom_chauffeur, matricule,
                            workshop_id
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (product_id, movement_type, quantity, notes, session['user_id'],
                          supplier_name, bc_number, bl_number, n_facture, type_achat,
                          chantier_exp_recep, nom_donneur_ordre, nom_magasinier, nom_chauffeur, matricule,
                          ws_id))

                    new_qty = current_quantity + quantity if movement_type == 'entry' else current_quantity - quantity
                    cursor.execute('UPDATE products SET quantity = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?',
                                  (new_qty, product_id))

                    cursor.execute('SELECT code, name FROM products WHERE id = ?', (product_id,))
                    product_row = cursor.fetchone()

                    if movement_type == 'entry':
                        send_product_addition_notification(
                            {'id': product_id, 'code': product_row['code'], 'name': product_row['name'],
                             'quantity': quantity, 'type_achat': type_achat,
                             'supplier_name': supplier_name, 'bc_number': bc_number, 'bl_number': bl_number,
                             'n_facture': n_facture, 'chantier_exp_recep': chantier_exp_recep,
                             'nom_donneur_ordre': nom_donneur_ordre, 'nom_chauffeur': nom_chauffeur,
                             'matricule': matricule},
                            'entry', session['username'], session.get('lang', 'fr'),
                            workshop_id=session.get('workshop_id'))
                    elif movement_type == 'exit':
                        send_product_exit_notification(
                            {'id': product_id, 'code': product_row['code'], 'name': product_row['name'],
                             'quantity': quantity, 'type_achat': type_achat, 'notes': notes,
                             'supplier_name': supplier_name, 'bc_number': bc_number, 'bl_number': bl_number,
                             'n_facture': n_facture, 'chantier_exp_recep': chantier_exp_recep,
                             'nom_donneur_ordre': nom_donneur_ordre, 'nom_chauffeur': nom_chauffeur,
                             'matricule': matricule},
                            'exit', session['username'], session.get('lang', 'fr'),
                            workshop_id=session.get('workshop_id'))

                log_audit('create', 'movement', cursor.lastrowid,
                          f"Mouvement {movement_type} de {quantity} pour produit #{product_id}")
                flash(get_translation('movement_added_successfully'), 'success')
                return redirect(url_for('movements'))
            except Exception as e:
                logger.error(f"Error adding movement: {e}")
                flash(f"Erreur lors de l'ajout: {str(e)}", 'error')

        with get_db() as conn:
            cursor = conn.cursor()
            ws_clause, ws_params = workshop_filter()
            cursor.execute('SELECT id, code, name, quantity FROM products WHERE deleted_at IS NULL' + ws_clause + ' ORDER BY name', ws_params)
            products_list = cursor.fetchall()
        return render_template('add_movement.html', products=products_list,
                             translations=TRANSLATIONS[session.get('lang', 'fr')],
                             lang=session.get('lang', 'fr'))

    @app.route('/edit_movement/<int:movement_id>', methods=['GET', 'POST'])
    @admin_required
    def edit_movement(movement_id):
        with get_db() as conn:
            cursor = conn.cursor()
            if request.method == 'POST':
                try:
                    movement_type = request.form['movement_type']
                    quantity = int(request.form['quantity'])
                    notes = request.form.get('notes', '').strip()
                    supplier_name = request.form.get('supplier_name', '').strip()
                    bc_number = request.form.get('bc_number', '').strip()
                    bl_number = request.form.get('bl_number', '').strip()
                    n_facture = request.form.get('n_facture', '').strip()
                    type_achat = request.form.get('type_achat', '').strip()
                    chantier_exp_recep = request.form.get('chantier_exp_recep', '').strip()
                    nom_donneur_ordre = request.form.get('nom_donneur_ordre', '').strip()
                    nom_magasinier = request.form.get('nom_magasinier', '').strip()
                    nom_chauffeur = request.form.get('nom_chauffeur', '').strip()
                    matricule = request.form.get('matricule', '').strip()

                    cursor.execute('SELECT * FROM stock_movements WHERE id = ?', (movement_id,))
                    old = cursor.fetchone()
                    if not old:
                        flash("Mouvement introuvable", 'error')
                        return redirect(url_for('movements'))
                    old_type, old_qty = old['movement_type'], old['quantity']

                    cursor.execute('SELECT quantity FROM products WHERE id = ?', (old['product_id'],))
                    prod = cursor.fetchone()
                    if not prod:
                        flash("Produit introuvable", 'error')
                        return redirect(url_for('movements'))

                    contrib = lambda t, q: q if t == 'entry' else -q
                    new_stock = prod['quantity'] + contrib(movement_type, quantity) - contrib(old_type, old_qty)
                    if new_stock < 0:
                        flash("Stock insuffisant : la correction ferait passer la quantité du produit en négatif", 'error')
                        return redirect(url_for('edit_movement', movement_id=movement_id))

                    cursor.execute('''
                        UPDATE stock_movements SET movement_type=?, quantity=?, notes=?,
                                                  supplier_name=?, bc_number=?, bl_number=?, n_facture=?,
                                                  type_achat=?, chantier_exp_recep=?, nom_donneur_ordre=?,
                                                  nom_magasinier=?, nom_chauffeur=?, matricule=?
                        WHERE id=?
                    ''', (movement_type, quantity, notes, supplier_name, bc_number, bl_number,
                          n_facture, type_achat, chantier_exp_recep, nom_donneur_ordre,
                          nom_magasinier, nom_chauffeur, matricule, movement_id))

                    cursor.execute('UPDATE products SET quantity=?, updated_at=CURRENT_TIMESTAMP WHERE id=?',
                                  (new_stock, old['product_id']))

                    old_values = {k: old[k] for k in old.keys()}
                    new_values = {
                        'movement_type': movement_type,
                        'quantity': quantity,
                        'notes': notes,
                        'supplier_name': supplier_name,
                        'bc_number': bc_number,
                        'bl_number': bl_number,
                        'n_facture': n_facture,
                        'type_achat': type_achat,
                        'chantier_exp_recep': chantier_exp_recep,
                        'nom_donneur_ordre': nom_donneur_ordre,
                        'nom_magasinier': nom_magasinier,
                        'nom_chauffeur': nom_chauffeur,
                        'matricule': matricule,
                    }
                    labels = {
                        'movement_type': 'Type',
                        'quantity': 'Quantité',
                        'notes': 'Notes',
                        'supplier_name': 'Fournisseur',
                        'bc_number': 'N° BC',
                        'bl_number': 'N° BL',
                        'n_facture': 'N° Facture',
                        'type_achat': "Type d'achat",
                        'chantier_exp_recep': 'Chantier',
                        'nom_donneur_ordre': "Donneur d'ordre",
                        'nom_magasinier': 'Magasinier',
                        'nom_chauffeur': 'Chauffeur',
                        'matricule': 'Matricule',
                    }
                    details = build_change_details(f"Correction du mouvement #{movement_id}",
                                                   old_values, new_values, labels)
                    log_audit('update', 'movement', movement_id, details)
                    flash("Mouvement corrigé avec succès", 'success')
                    return redirect(url_for('movements'))
                except Exception as e:
                    logger.error(f"Error updating movement: {e}")
                    flash(f"Erreur lors de la correction: {str(e)}", 'error')

            cursor.execute('SELECT * FROM stock_movements WHERE id = ?', (movement_id,))
            movement = cursor.fetchone()
            if not movement:
                flash("Mouvement introuvable", 'error')
                return redirect(url_for('movements'))
            cursor.execute('SELECT id, code, name FROM products WHERE id = ?', (movement['product_id'],))
            product = cursor.fetchone()

        return render_template('edit_movement.html', movement=movement, product=product,
                             translations=TRANSLATIONS[session.get('lang', 'fr')],
                             lang=session.get('lang', 'fr'))

    @app.route('/delete_movement/<int:movement_id>')
    @admin_required
    def delete_movement(movement_id):
        try:
            with get_db() as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT product_id, movement_type, quantity FROM stock_movements WHERE id = ?', (movement_id,))
                movement = cursor.fetchone()
                if not movement:
                    flash("Mouvement introuvable", 'error')
                    return redirect(url_for('movements'))
                cursor.execute('SELECT quantity FROM products WHERE id = ?', (movement['product_id'],))
                prod = cursor.fetchone()
                if not prod:
                    flash("Produit introuvable", 'error')
                    return redirect(url_for('movements'))
                new_stock = prod['quantity'] + (movement['quantity'] if movement['movement_type'] == 'exit' else -movement['quantity'])
                if new_stock < 0:
                    flash("Suppression impossible : le stock du produit deviendrait négatif", 'error')
                    return redirect(url_for('movements'))
                cursor.execute('DELETE FROM stock_movements WHERE id = ?', (movement_id,))
                cursor.execute('UPDATE products SET quantity=?, updated_at=CURRENT_TIMESTAMP WHERE id=?',
                              (new_stock, movement['product_id']))
                log_audit('delete', 'movement', movement_id,
                          f"Suppression du mouvement #{movement_id} ({movement['movement_type']} {movement['quantity']})")
            flash("Mouvement supprimé avec succès", 'success')
        except Exception as e:
            logger.error(f"Error deleting movement: {e}")
            flash(f"Erreur lors de la suppression: {str(e)}", 'error')
        return redirect(url_for('movements'))

    @app.route('/movement_reports')
    @login_required
    def movement_reports():
        with get_db() as conn:
            cursor = conn.cursor()
            start_date = request.args.get('start_date', '')
            end_date = request.args.get('end_date', '')
            movement_type = request.args.get('movement_type', '')

            q = '''
                SELECT sm.id, sm.movement_type, sm.quantity, sm.notes, sm.created_at,
                       p.code, p.name, u.username, sm.supplier_name, sm.type_achat,
                       sm.chantier_exp_recep, sm.nom_donneur_ordre, sm.nom_magasinier,
                       sm.nom_chauffeur, sm.matricule
                FROM stock_movements sm
                JOIN products p ON sm.product_id = p.id
                JOIN users u ON sm.user_id = u.id
                WHERE 1=1
            '''
            params = []
            ws_clause, ws_params = workshop_filter('sm')
            q += ws_clause
            params.extend(ws_params)
            if start_date:
                q += ' AND DATE(sm.created_at) >= ?'
                params.append(start_date)
            if end_date:
                q += ' AND DATE(sm.created_at) <= ?'
                params.append(end_date)
            if movement_type:
                q += ' AND sm.movement_type = ?'
                params.append(movement_type)
            q += ' ORDER BY sm.created_at DESC'
            cursor.execute(q, params)
            movements_data = cursor.fetchall()

            sq = '''SELECT movement_type, COUNT(*), SUM(quantity) FROM stock_movements sm WHERE 1=1'''
            sp = []
            if start_date:
                sq += ' AND DATE(sm.created_at) >= ?'
                sp.append(start_date)
            if end_date:
                sq += ' AND DATE(sm.created_at) <= ?'
                sp.append(end_date)
            sq += ' GROUP BY movement_type'
            cursor.execute(sq, sp)
            summary_data = cursor.fetchall()

        return render_template('movement_reports.html', movements=movements_data, summary=summary_data,
                             start_date=start_date, end_date=end_date, movement_type=movement_type,
                             translations=TRANSLATIONS[session.get('lang', 'fr')],
                             lang=session.get('lang', 'fr'))

    @app.route('/export_movements_excel')
    @login_required
    def export_movements_excel():
        try:
            with get_db() as conn:
                cursor = conn.cursor()
                start_date = request.args.get('start_date', '')
                end_date = request.args.get('end_date', '')
                movement_type = request.args.get('movement_type', '')

                q = '''
                    SELECT sm.created_at, sm.movement_type, p.code, p.name, sm.quantity,
                           sm.notes, u.username, sm.supplier_name, sm.bc_number, sm.bl_number,
                           sm.n_facture, sm.type_achat, sm.chantier_exp_recep, sm.nom_donneur_ordre,
                           sm.nom_magasinier, sm.nom_chauffeur, sm.matricule
                    FROM stock_movements sm
                    JOIN products p ON sm.product_id = p.id
                    JOIN users u ON sm.user_id = u.id
                    WHERE 1=1
                '''
                params = []
                ws_clause, ws_params = workshop_filter('sm')
                q += ws_clause
                params.extend(ws_params)
                if start_date:
                    q += ' AND DATE(sm.created_at) >= ?'
                    params.append(start_date)
                if end_date:
                    q += ' AND DATE(sm.created_at) <= ?'
                    params.append(end_date)
                if movement_type:
                    q += ' AND sm.movement_type = ?'
                    params.append(movement_type)
                q += ' ORDER BY sm.created_at DESC'
                cursor.execute(q, params)
                movements_data = cursor.fetchall()

            headers = [
                'Date', 'Type de Mouvement', 'Code Produit', 'Nom du Produit', 'Quantité',
                'Notes', 'Utilisateur', 'Nom Fournisseur', 'Numéro BC', 'Numéro BL',
                'Numéro Facture', "Type d'Achat", 'Chantier/Exp/Récep', "Donneur d'ordre",
                'Magasinier', 'Chauffeur', 'Matricule'
            ]

            output = BytesIO()
            workbook = xlsxwriter.Workbook(output)
            worksheet = workbook.add_worksheet('Mouvements')
            header_fmt = workbook.add_format({'bold': True, 'bg_color': '#D3D3D3', 'font_size': 12, 'align': 'center', 'border': 1})
            data_fmt = workbook.add_format({'font_size': 11, 'border': 1})
            for col, header in enumerate(headers):
                worksheet.write(0, col, header, header_fmt)
            for r_idx, movement in enumerate(movements_data, 1):
                for c_idx, value in enumerate(movement):
                    if c_idx == 0:
                        try:
                            date_obj = datetime.strptime(str(value), '%Y-%m-%d %H:%M:%S')
                            worksheet.write_datetime(r_idx, c_idx, date_obj, data_fmt)
                        except (ValueError, TypeError):
                            try:
                                date_obj = excel_serial_to_datetime(float(value))
                                worksheet.write_datetime(r_idx, c_idx, date_obj, data_fmt)
                            except (ValueError, TypeError, OverflowError):
                                worksheet.write(r_idx, c_idx, str(value), data_fmt)
                    else:
                        worksheet.write(r_idx, c_idx, value if value is not None else '', data_fmt)
            for col in range(len(headers)):
                worksheet.set_column(col, col, 18)
            workbook.close()
            output.seek(0)

            return Response(
                output.getvalue(),
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                headers={'Content-Disposition': f'attachment; filename=rapport_mouvements_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx'}
            )
        except Exception as e:
            logger.error(f"Error exporting movements: {e}")
            flash(f"Erreur lors de l'export: {str(e)}", 'error')
            return redirect(url_for('movement_reports'))
