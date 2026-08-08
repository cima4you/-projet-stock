import os
import logging
from io import BytesIO
from datetime import datetime
from flask import render_template, session, request, Response, redirect, url_for, flash
from utils import login_required, admin_required, get_translation, log_audit, workshop_filter, parse_change_details
from translations import TRANSLATIONS
from db import get_db, query, query_one
from config import LOGO_FOLDER

logger = logging.getLogger(__name__)


def register_report_routes(app):

    @app.route('/reports')
    @login_required
    def reports():
        return render_template('reports.html',
                             translations=TRANSLATIONS[session.get('lang', 'fr')],
                             lang=session.get('lang', 'fr'))

    @app.route('/audit_log')
    @admin_required
    def audit_log():
        per_page = 50

        username_filter = request.args.get('username', '').strip()
        action_filter = request.args.get('action', '').strip()
        date_from = request.args.get('date_from', '').strip()
        date_to = request.args.get('date_to', '').strip()
        laction = request.args.get('laction', '').strip()

        def filters(table):
            where = ' WHERE 1=1'
            params = []
            if username_filter:
                where += f' AND {table}.username LIKE ?'
                params.append(f'%{username_filter}%')
            if date_from:
                where += f' AND DATE({table}.created_at) >= ?'
                params.append(date_from)
            if date_to:
                where += f' AND DATE({table}.created_at) <= ?'
                params.append(date_to)
            return where, params

        # Modifications (audit_log)
        page = request.args.get('page', 1, type=int)
        offset = (page - 1) * per_page
        where, params = filters('al')
        if action_filter:
            where += ' AND al.action = ?'
            params.append(action_filter)
        total = query_one('SELECT COUNT(*) as cnt FROM audit_log al' + where, tuple(params))
        total = total['cnt'] if total else 0
        logs = query('SELECT al.* FROM audit_log al' + where + ' ORDER BY al.created_at DESC LIMIT ? OFFSET ?',
                     tuple(params + [per_page, offset]))
        total_pages = max(1, (total + per_page - 1) // per_page)

        logs = [dict(log) for log in logs]
        for log in logs:
            parsed = parse_change_details(log.get('details'))
            if parsed:
                log['changes'] = parsed.get('changes', [])
                log['summary'] = parsed.get('summary', log.get('details', ''))
                log['has_changes'] = True
            else:
                log['has_changes'] = False

        # Connexions / déconnexions (login_logs)
        lpage = request.args.get('lpage', 1, type=int)
        loffset = (lpage - 1) * per_page
        lwhere, lparams = filters('ll')
        if laction:
            lwhere += ' AND ll.action = ?'
            lparams.append(laction)
        ltotal = query_one('SELECT COUNT(*) as cnt FROM login_logs ll' + lwhere, tuple(lparams))
        ltotal = ltotal['cnt'] if ltotal else 0
        login_logs = query('SELECT ll.* FROM login_logs ll' + lwhere + ' ORDER BY ll.created_at DESC LIMIT ? OFFSET ?',
                           tuple(lparams + [per_page, loffset]))
        ltotal_pages = max(1, (ltotal + per_page - 1) // per_page)

        return render_template('audit_log.html', logs=logs, login_logs=login_logs,
                             page=page, total_pages=total_pages,
                             lpage=lpage, ltotal_pages=ltotal_pages,
                             username_filter=username_filter, action_filter=action_filter,
                             date_from=date_from, date_to=date_to, laction=laction,
                             translations=TRANSLATIONS[session.get('lang', 'fr')],
                             lang=session.get('lang', 'fr'))

    @app.route('/export_pdf_products')
    @login_required
    def export_pdf_products():
        try:
            from fpdf import FPDF
            ws_clause, ws_params = workshop_filter()
            rows = query('SELECT * FROM products WHERE deleted_at IS NULL' + ws_clause + ' ORDER BY name', tuple(ws_params))
            pdf = _build_products_pdf(rows)
            return Response(pdf.getvalue(), mimetype='application/pdf',
                           headers={'Content-Disposition': f'attachment; filename=produits_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf'})
        except Exception as e:
            logger.error(f"PDF export error: {e}")
            flash(f"Erreur d'export PDF: {str(e)}", 'error')
            return redirect(url_for('reports'))

    @app.route('/export_pdf_movements')
    @login_required
    def export_pdf_movements():
        try:
            from fpdf import FPDF
            ws_clause, ws_params = workshop_filter('sm')
            rows = query('''
                SELECT sm.created_at, sm.movement_type, p.code, p.name, p.category, sm.quantity,
                       u.username, sm.supplier_name, sm.bc_number, sm.bl_number,
                       sm.n_facture, sm.type_achat, sm.chantier_exp_recep,
                       sm.nom_donneur_ordre, sm.nom_magasinier, sm.nom_chauffeur,
                       sm.matricule
                FROM stock_movements sm
                JOIN products p ON sm.product_id = p.id
                JOIN users u ON sm.user_id = u.id
                WHERE 1=1''' + ws_clause + '''
                ORDER BY sm.created_at DESC LIMIT 500
            ''', tuple(ws_params))
            pdf = _build_movements_pdf(rows)
            return Response(pdf.getvalue(), mimetype='application/pdf',
                           headers={'Content-Disposition': f'attachment; filename=mouvements_{datetime.now().strftime("%Y%m%d_%H%M%S")}.pdf'})
        except Exception as e:
            logger.error(f"PDF export error: {e}")
            flash(f"Erreur d'export PDF: {str(e)}", 'error')
            return redirect(url_for('reports'))


def _add_logo(pdf):
    logo_path = os.path.join(LOGO_FOLDER, 'logo.png')
    if os.path.exists(logo_path):
        pdf.image(logo_path, x=10, y=8, w=30)


def _build_products_pdf(rows):
    from fpdf import FPDF
    pdf = FPDF(orientation='L')
    pdf.add_page()
    _add_logo(pdf)
    pdf.set_font('Helvetica', 'B', 16)
    pdf.cell(0, 10, 'Rapport des Produits', new_x="LMARGIN", new_y="NEXT", align='C')
    pdf.set_font('Helvetica', '', 9)
    pdf.cell(0, 6, f"Generé le {datetime.now().strftime('%Y-%m-%d %H:%M')}", new_x="LMARGIN", new_y="NEXT", align='C')
    pdf.ln(5)
    cols = ['ID', 'Code Produit', 'Nom du Produit', 'Catégorie', 'Unité', 'Quantité',
            'Marque', 'État', 'Chantier', 'Zone Stockage', 'Fournisseur',
            'N° BC', 'N° BL', 'N° Facture', "Type d'Achat", "Date d'Exp.",
            'Créé le']
    widths = [8, 20, 35, 18, 10, 10, 16, 10, 16, 16, 22, 16, 16, 16, 18, 18, 18]
    pdf.set_font('Helvetica', 'B', 6)
    pdf.set_fill_color(78, 115, 223)
    pdf.set_text_color(255, 255, 255)
    for i, col in enumerate(cols):
        pdf.cell(widths[i], 7, col, border=1, align='C', fill=True)
    pdf.ln()
    pdf.set_font('Helvetica', '', 5.5)
    pdf.set_text_color(0, 0, 0)
    fill = False
    for r in rows:
        if pdf.get_y() > 190:
            pdf.add_page()
            pdf.set_font('Helvetica', 'B', 6)
            pdf.set_fill_color(78, 115, 223)
            pdf.set_text_color(255, 255, 255)
            for i, col in enumerate(cols):
                pdf.cell(widths[i], 7, col, border=1, align='C', fill=True)
            pdf.ln()
            pdf.set_font('Helvetica', '', 5.5)
            pdf.set_text_color(0, 0, 0)
        data = [
            str(r[0]), str(r[1])[:18], str(r[2])[:25], str(r[3] or '-')[:12],
            str(r[4] or '-')[:6], str(r[5]), str(r[6] or '-')[:10],
            str(r[7] or '-')[:6], str(r[8] or '-')[:10], str(r[9] or '-')[:10],
            str(r[11] or '-')[:14], str(r[12] or '-')[:10], str(r[13] or '-')[:10],
            str(r[14] or '-')[:10], str(r[15] or '-')[:12],
            str(r[16] or '-')[:10], str(r[17] or '')[:10]
        ]
        if fill:
            pdf.set_fill_color(240, 240, 240)
        else:
            pdf.set_fill_color(255, 255, 255)
        for i, d in enumerate(data):
            pdf.cell(widths[i], 5, d, border=1, align='C' if i < 2 else 'L', fill=True)
        pdf.ln()
        fill = not fill
    buf = BytesIO()
    pdf.output(buf)
    buf.seek(0)
    return buf


def _build_movements_pdf(rows):
    from fpdf import FPDF
    pdf = FPDF(orientation='L')
    pdf.add_page()
    _add_logo(pdf)
    pdf.set_font('Helvetica', 'B', 16)
    pdf.cell(0, 10, 'Rapport des Mouvements', new_x="LMARGIN", new_y="NEXT", align='C')
    pdf.set_font('Helvetica', '', 9)
    pdf.cell(0, 6, f"Generé le {datetime.now().strftime('%Y-%m-%d %H:%M')}", new_x="LMARGIN", new_y="NEXT", align='C')
    pdf.ln(5)
    cols = ['Date', 'Type', 'Code Produit', 'Nom Produit', 'Catégorie', 'Qté', 'Utilisateur',
            'Fournisseur', 'N° BC', 'N° BL', 'N° Facture', "Type d'Achat",
            'Chantier/Exp', "Donneur d'ordre", 'Magasinier', 'Chauffeur', 'Matricule']
    widths = [18, 10, 20, 30, 16, 9, 16, 18, 15, 15, 15, 15, 18, 18, 16, 16, 11]
    pdf.set_font('Helvetica', 'B', 6)
    pdf.set_fill_color(78, 115, 223)
    pdf.set_text_color(255, 255, 255)
    for i, col in enumerate(cols):
        pdf.cell(widths[i], 7, col, border=1, align='C', fill=True)
    pdf.ln()
    pdf.set_font('Helvetica', '', 5.5)
    pdf.set_text_color(0, 0, 0)
    fill = False
    for r in rows:
        if pdf.get_y() > 190:
            pdf.add_page()
            pdf.set_font('Helvetica', 'B', 6)
            pdf.set_fill_color(78, 115, 223)
            pdf.set_text_color(255, 255, 255)
            for i, col in enumerate(cols):
                pdf.cell(widths[i], 7, col, border=1, align='C', fill=True)
            pdf.ln()
            pdf.set_font('Helvetica', '', 5.5)
            pdf.set_text_color(0, 0, 0)
        t = 'Entrée' if r[1] == 'entry' else 'Sortie'
        data = [
            str(r[0])[:10], t, str(r[2])[:14], str(r[3])[:22], str(r[4] or '-')[:12], str(r[5]),
            str(r[6])[:12], str(r[7] or '-')[:14], str(r[8] or '-')[:10],
            str(r[9] or '-')[:10], str(r[10] or '-')[:10], str(r[11] or '-')[:12],
            str(r[12] or '-')[:14], str(r[13] or '-')[:14], str(r[14] or '-')[:12],
            str(r[15] or '-')[:12], str(r[16] or '-')[:10]
        ]
        if fill:
            pdf.set_fill_color(240, 240, 240)
        else:
            pdf.set_fill_color(255, 255, 255)
        for i, d in enumerate(data):
            pdf.cell(widths[i], 5, d, border=1, align='C' if i < 3 else 'L', fill=True)
        pdf.ln()
        fill = not fill
    buf = BytesIO()
    pdf.output(buf)
    buf.seek(0)
    return buf
