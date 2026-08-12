import os
import smtplib
import logging
import xlsxwriter
from io import BytesIO
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.image import MIMEImage
import email.encoders as encoders
from typing import Optional
from config import SMTP_SERVER, SMTP_PORT, EMAIL_ADDRESS, EMAIL_PASSWORD, NOTIFICATION_EMAIL, LOGO_FOLDER
from db import get_db, query, query_one, execute
from utils import excel_serial_to_datetime

logger = logging.getLogger(__name__)


def _embed_logo(html: str) -> tuple:
    logo_path = os.path.join(LOGO_FOLDER, 'logo.png')
    if not os.path.exists(logo_path):
        return html, None
    logo_tag = '<img src="cid:logo" alt="Logo" style="max-height: 60px; margin-bottom: 10px;">'
    if '<div class="header">' in html:
        html = html.replace('<div class="header">', f'<div class="header">{logo_tag}<br>')
    elif '<body' in html and ('</h1>' in html or '</h2>' in html):
        tag = '</h1>' if '</h1>' in html else '</h2>'
        html = html.replace(tag, f'{tag}<br>{logo_tag}')
    else:
        html = html.replace('<body>', f'<body>{logo_tag}')
    return html, logo_path


def send_email(to_email: str, subject: str, body: str, html_body: Optional[str] = None) -> bool:
    try:
        if not EMAIL_ADDRESS or not EMAIL_PASSWORD:
            logger.error("Email credentials not configured")
            return False

        if html_body:
            html_body, logo_path = _embed_logo(html_body)
        else:
            logo_path = None

        msg = MIMEMultipart('related') if (logo_path and html_body) else MIMEMultipart('alternative')
        msg['From'] = EMAIL_ADDRESS
        msg['To'] = to_email
        msg['Subject'] = subject

        alt = MIMEMultipart('alternative')
        alt.attach(MIMEText(body, 'plain', 'utf-8'))
        if html_body:
            alt.attach(MIMEText(html_body, 'html', 'utf-8'))

        if logo_path and html_body:
            msg.attach(alt)
            with open(logo_path, 'rb') as f:
                logo_img = MIMEImage(f.read())
                logo_img.add_header('Content-ID', '<logo>')
                logo_img.add_header('Content-Disposition', 'inline', filename='logo.png')
                msg.attach(logo_img)
        else:
            msg = alt

        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        server.sendmail(EMAIL_ADDRESS, to_email, msg.as_string())
        server.quit()
        logger.info(f"Email sent to {to_email}")
        return True
    except Exception as e:
        logger.error(f"Failed to send email to {to_email}: {e}")
        return False


def log_notification(recipient_email: str, notification_type: str, subject: str,
                     content: Optional[str] = None, product_id: Optional[int] = None,
                     status: str = 'sent'):
    try:
        execute('''
            INSERT INTO notification_logs (recipient_email, notification_type, subject, content, product_id, status)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (recipient_email, notification_type, subject, content, product_id, status))
    except Exception as e:
        logger.error(f"Failed to log notification: {e}")


def send_product_deletion_notification(product_info: dict, deleted_by_user: str, workshop_id=None):
    try:
        ws_filter = ' AND (nr.workshop_id = ? OR nr.workshop_id IS NULL)' if workshop_id else ''
        recipients = query('''
            SELECT nr.name, re.email FROM recipient_emails re
            JOIN notification_recipients nr ON re.recipient_id = nr.id
            WHERE re.active = 1 AND re.notify_product_deletion = 1''' + ws_filter,
            (workshop_id,) if workshop_id else ())
        if not recipients:
            return

        subject = f"Produit supprimé - {product_info['name']}"
        html_body = _load_template('email_templates/product_deleted_fr.html', {
            'product_name': product_info['name'],
            'product_code': product_info['code'],
            'deleted_by': deleted_by_user,
            'deletion_date': datetime.now().strftime('%Y-%m-%d %H:%M')
        }) or _fallback_html('deletion', product_info, deleted_by_user)
        body = f"Produit supprimé du stock\nNom du produit: {product_info['name']}\nCode produit: {product_info['code']}\nSupprimé par: {deleted_by_user}\nDate de suppression: {datetime.now().strftime('%Y-%m-%d %H:%M')}\nCeci est une notification automatique du système de gestion de stock."

        for recipient in recipients:
            success = send_email(recipient['email'], subject, body, html_body)
            log_notification(recipient['email'], 'product_deletion', subject, body,
                             product_id=product_info.get('id'), status='sent' if success else 'failed')

    except Exception as e:
        logger.error(f"Failed to send deletion notification: {e}")


def send_product_addition_notification(product_info: dict, movement_type: str, added_by_user: str, workshop_id=None):
    try:
        type_mapping = {
            'achat_par_bc': 'BC', 'achat_par_caisse': 'Caisse',
            'achat_a_regulariser': 'À régulariser', 'transfert': 'Transfert',
            'consommation': 'Consommation', 'perte': 'Perte',
            'vendu': 'Vendu', 'expire': 'Expiré'
        }
        raw_type = product_info.get('type_achat', '').strip()
        normalized_type = type_mapping.get(raw_type, raw_type)

        ws_filter = ' AND (nr.workshop_id = ? OR nr.workshop_id IS NULL)' if workshop_id else ''
        ws_params = (workshop_id,) if workshop_id else ()
        notification_fields = {
            'BC': 're.notify_achat_par_bc', 'Caisse': 're.notify_achat_par_caisse',
            'À régulariser': 're.notify_achat_a_regulariser', 'Transfert': 're.notify_transfert', 'Consommation': 're.notify_consumption'
        }
        field = notification_fields.get(normalized_type)
        if field:
            recipients = query(f'SELECT nr.name, re.email FROM recipient_emails re JOIN notification_recipients nr ON re.recipient_id = nr.id WHERE re.active = 1 AND {field} = 1' + ws_filter, ws_params)
        else:
            recipients = query('''
                SELECT nr.name, re.email FROM recipient_emails re
                JOIN notification_recipients nr ON re.recipient_id = nr.id
                WHERE re.active = 1 AND (re.notify_achat_par_bc = 1 OR re.notify_achat_par_caisse = 1
                OR re.notify_achat_a_regulariser = 1 OR re.notify_transfert = 1 OR re.notify_consumption = 1)
            ''' + ws_filter, ws_params)
        if not recipients:
            return

        type_labels = {
            'BC': 'Achat par BC',
            'Caisse': 'Achat par Caisse',
            'À régulariser': 'Achat à Régulariser',
            'Transfert': 'Transfert',
            'Consommation': 'Consommation interne',
        }
        type_label = type_labels.get(normalized_type, 'Inconnu')

        extra_fields = [
            ('supplier_name', 'Nom Fournisseur'),
            ('bc_number', 'Numéro BC'),
            ('bl_number', 'Numéro BL'),
            ('n_facture', 'Numéro Facture'),
            ('chantier_exp_recep', 'Chantier/Exp/Récep'),
            ('nom_donneur_ordre', "Donneur d'ordre"),
            ('nom_magasinier', 'Magasinier'),
            ('nom_chauffeur', 'Chauffeur'),
            ('matricule', 'Matricule'),
        ]

        def build_extra(sep, fmt):
            parts = []
            for key, fr_label in extra_fields:
                val = str(product_info.get(key, '')).strip()
                if val:
                    parts.append(fmt(fr_label, val))
            return sep.join(parts)

        extra_text = build_extra('\n', lambda l, v: f"{l}: {v}")
        extra_html = build_extra('', lambda l, v: f"<p><strong>{l}:</strong> {v}</p>")

        subject = f"Nouveau produit ajouté - {product_info['name']}"
        body = (f"Nouveau produit ajouté au stock\nNom du produit: {product_info['name']}\n"
                f"Code produit: {product_info['code']}\nQuantité: {product_info['quantity']}\n"
                f"Type de mouvement: {type_label}\n"
                f"{extra_text}\n" if extra_text else ""
                f"Ajouté par: {added_by_user}\nDate d'ajout: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n"
                f"Ceci est une notification automatique du système de gestion de stock.")
        html_body = (f"""<html><body style="font-family: Arial, sans-serif;">"""
                    f"""<div class="header" style="text-align:center;margin-bottom:20px;padding-bottom:20px;border-bottom:2px solid #007bff;">"""
                    f"""<h2 style="color:#007bff;">Nouveau produit ajouté</h2></div>"""
                    f"""<p><strong>Nom du produit:</strong> {product_info['name']}</p>"""
                    f"""<p><strong>Code produit:</strong> {product_info['code']}</p>"""
                    f"""<p><strong>Quantité:</strong> {product_info['quantity']}</p>"""
                    f"""<p><strong>Type de mouvement:</strong> {type_label}</p>"""
                    f"""{extra_html}"""
                    f"""<p><strong>Ajouté par:</strong> {added_by_user}</p>"""
                    f"""<p><strong>Date d'ajout:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>"""
                    f"""<p>Ceci est une notification automatique du système de gestion de stock.</p></body></html>""")

        for recipient in recipients:
            success = send_email(recipient['email'], subject, body, html_body)
            log_notification(recipient['email'], 'product_addition', subject, body,
                             product_id=product_info.get('id'), status='sent' if success else 'failed')

    except Exception as e:
        logger.error(f"Failed to send addition notification: {e}")


def send_product_exit_notification(product_info: dict, movement_type: str, removed_by_user: str, workshop_id=None):
    try:
        if movement_type != 'exit':
            return

        notify_field_map = {
            'transfert': 'notify_transfert', 'consommation': 'notify_consumption',
            'perte': 'notify_transfert', 'vendu': 'notify_transfert',
            'expire': 'notify_transfert'
        }
        exit_type = product_info.get('type_achat', '')
        notify_field = notify_field_map.get(exit_type)
        if not notify_field:
            return
        ws_filter = ' AND (nr.workshop_id = ? OR nr.workshop_id IS NULL)' if workshop_id else ''
        ws_params = (workshop_id,) if workshop_id else ()
        recipients = query(f'''
            SELECT nr.name, re.email FROM recipient_emails re
            JOIN notification_recipients nr ON re.recipient_id = nr.id
            WHERE re.active = 1 AND re.{notify_field} = 1''' + ws_filter, ws_params)
        if not recipients:
            return

        notes = product_info.get('notes', '').strip()
        has_notes = bool(notes)
        type_labels = {
            'transfert': 'Transfert',
            'consommation': 'Consommation interne',
            'perte': 'Perte',
            'vendu': 'Vendu',
            'expire': 'Expiré'
        }
        type_label = type_labels.get(exit_type, 'Inconnu')

        extra_fields = [
            ('supplier_name', 'Nom Fournisseur'),
            ('bc_number', 'Numéro BC'),
            ('bl_number', 'Numéro BL'),
            ('n_facture', 'Numéro Facture'),
            ('chantier_exp_recep', 'Chantier/Exp/Récep'),
            ('nom_donneur_ordre', "Donneur d'ordre"),
            ('nom_chauffeur', 'Chauffeur'),
            ('matricule', 'Matricule'),
        ]

        def build_extra_text(sep, fmt):
            parts = []
            for key, fr_label in extra_fields:
                val = str(product_info.get(key, '')).strip()
                if val:
                    parts.append(fmt(fr_label, val))
            return sep.join(parts)

        extra_text = build_extra_text('\n', lambda l, v: f"{l}: {v}")
        extra_html = build_extra_text('', lambda l, v: f"<p><strong>{l}:</strong> {v}</p>")

        subject = f"Sortie de produit - {product_info['name']}"
        notes_text = f"\nNote: {notes}\n" if has_notes else ""
        notes_html = f"<p><strong>Note:</strong> {notes}</p>" if has_notes else ""
        body = (f"Sortie de produit du stock\nNom du produit: {product_info['name']}\n"
                f"Code produit: {product_info['code']}\nQuantité: {product_info['quantity']}\n"
                f"Type de sortie: {type_label}\n"
                f"{extra_text}\n" if extra_text else ""
                f"Retiré par: {removed_by_user}\n"
                f"Date de sortie: {datetime.now().strftime('%Y-%m-%d %H:%M')}{notes_text}"
                f"Ceci est une notification automatique du système de gestion de stock.")
        html_body = (f"""<html><body style="font-family: Arial, sans-serif;">"""
                    f"""<div class="header" style="text-align:center;margin-bottom:20px;padding-bottom:20px;border-bottom:2px solid #dc3545;">"""
                    f"""<h2 style="color:#dc3545;">Sortie de produit</h2></div>"""
                    f"""<p><strong>Nom du produit:</strong> {product_info['name']}</p>"""
                    f"""<p><strong>Code produit:</strong> {product_info['code']}</p>"""
                    f"""<p><strong>Quantité:</strong> {product_info['quantity']}</p>"""
                    f"""<p><strong>Type de sortie:</strong> {type_label}</p>"""
                    f"""{extra_html}"""
                    f"""<p><strong>Retiré par:</strong> {removed_by_user}</p>"""
                    f"""<p><strong>Date de sortie:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>"""
                    f"""{notes_html}<p>Ceci est une notification automatique du système de gestion de stock.</p></body></html>""")

        for recipient in recipients:
            success = send_email(recipient['email'], subject, body, html_body)
            log_notification(recipient['email'], 'product_exit', subject, body,
                             product_id=product_info.get('id'), status='sent' if success else 'failed')

    except Exception as e:
        logger.error(f"Failed to send exit notification: {e}")


def send_expiring_products_notification(expiring_products: list, workshop_id=None):
    try:
        ws_filter = ' AND (nr.workshop_id = ? OR nr.workshop_id IS NULL)' if workshop_id else ''
        ws_params = (workshop_id,) if workshop_id else ()
        recipients = query('''
            SELECT nr.name, re.email FROM recipient_emails re
            JOIN notification_recipients nr ON re.recipient_id = nr.id
            WHERE re.active = 1 AND re.notify_product_expiration = 1''' + ws_filter, ws_params)
        if not recipients or not expiring_products:
            return

        subject = f"Produits expirant bientôt - {len(expiring_products)} produits"
        products_rows = ""
        for p in expiring_products:
            days = (datetime.strptime(p['expiration_date'], '%Y-%m-%d').date() - datetime.now().date()).days
            products_rows += f"<tr><td>{p['name']}</td><td>{p['code']}</td><td>{p['expiration_date']}</td><td>{days} jours</td></tr>"
        html_body = f"""<html><body style="font-family: Arial, sans-serif;"><div class="header" style="text-align:center;margin-bottom:20px;padding-bottom:20px;border-bottom:2px solid #ffc107;"><h2 style="color:#ffc107;">Produits expirant bientôt</h2></div><p>{len(expiring_products)} produits approchent de leur date d'expiration :</p><table border="1" style="border-collapse: collapse; width: 100%;"><tr><th>Nom du produit</th><th>Code</th><th>Date d'expiration</th><th>Jours restants</th></tr>{products_rows}</table><p>Date de vérification: {datetime.now().strftime('%Y-%m-%d %H:%M')}</p><p>Ceci est une notification automatique du système de gestion de stock.</p></body></html>"""
        body = f"Produits expirant bientôt\n{len(expiring_products)} produits approchent de leur date d'expiration :\n"
        for p in expiring_products:
            days = (datetime.strptime(p['expiration_date'], '%Y-%m-%d').date() - datetime.now().date()).days
            body += f"- {p['name']} ({p['code']}) - expire dans {days} jours\n"

        for recipient in recipients:
            success = send_email(recipient['email'], subject, body, html_body)
            log_notification(recipient['email'], 'product_expiration', subject, body,
                             status='sent' if success else 'failed')

    except Exception as e:
        logger.error(f"Failed to send expiration notification: {e}")


def send_password_reset_email(to_email: str, reset_token: str) -> bool:
    from flask import request
    reset_url = f"{request.host_url}reset_password/{reset_token}"
    subject = "Réinitialisation du mot de passe - Système de gestion de stock"
    body = f"Réinitialisation du mot de passe\nNous avons reçu une demande de réinitialisation de votre mot de passe.\nCopiez et collez le lien suivant: {reset_url}\nSi vous n'avez pas demandé de réinitialisation, veuillez ignorer cet email.\nCe lien est valide pendant une heure seulement."
    html_body = f"""<html><body style="font-family: Arial, sans-serif;"><div class="header" style="text-align:center;margin-bottom:20px;padding-bottom:20px;border-bottom:2px solid #007bff;"><h2 style="color:#007bff;">Réinitialisation du mot de passe</h2></div><p>Nous avons reçu une demande de réinitialisation de votre mot de passe.</p><p><a href="{reset_url}" style="background: #007bff; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">Réinitialiser le mot de passe</a></p><p>Si vous n'avez pas demandé de réinitialisation, veuillez ignorer cet email.</p><p>Ce lien est valide pendant une heure seulement.</p></body></html>"""
    return send_email(to_email, subject, body, html_body)


def _add_logo_pdf(pdf):
    logo_path = os.path.join(LOGO_FOLDER, 'logo.png')
    if os.path.exists(logo_path):
        pdf.image(logo_path, x=10, y=8, w=30)


def _generate_products_pdf() -> BytesIO:
    from fpdf import FPDF
    rows = query('SELECT * FROM products WHERE deleted_at IS NULL ORDER BY name')
    pdf = FPDF(orientation='L')
    pdf.add_page()
    _add_logo_pdf(pdf)
    pdf.set_font('Helvetica', 'B', 16)
    pdf.cell(0, 10, 'Rapport des Produits', new_x="LMARGIN", new_y="NEXT", align='C')
    pdf.set_font('Helvetica', '', 9)
    pdf.cell(0, 6, f"Genere le {datetime.now().strftime('%Y-%m-%d %H:%M')}", new_x="LMARGIN", new_y="NEXT", align='C')
    pdf.ln(5)
    cols = ['ID', 'Code Produit', 'Nom du Produit', 'Catégorie', 'Unité', 'Quantité',
            'Marque', 'État', 'Chantier', 'Zone Stockage', 'Fournisseur',
            'N° BC', 'N° BL', 'N° Facture', "Type d'Achat", "Date d'Exp.", 'Créé le']
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


def _generate_movements_pdf() -> BytesIO:
    from fpdf import FPDF
    rows = query('''
        SELECT sm.created_at, sm.movement_type, p.code, p.name, p.category, sm.quantity,
               u.username, sm.supplier_name, sm.bc_number, sm.bl_number,
               sm.n_facture, sm.type_achat, sm.chantier_exp_recep,
               sm.nom_donneur_ordre, sm.nom_magasinier, sm.nom_chauffeur, sm.matricule
        FROM stock_movements sm
        JOIN products p ON sm.product_id = p.id
        JOIN users u ON sm.user_id = u.id
        ORDER BY sm.created_at DESC
    ''')
    pdf = FPDF(orientation='L')
    pdf.add_page()
    _add_logo_pdf(pdf)
    pdf.set_font('Helvetica', 'B', 16)
    pdf.cell(0, 10, 'Rapport des Mouvements', new_x="LMARGIN", new_y="NEXT", align='C')
    pdf.set_font('Helvetica', '', 9)
    pdf.cell(0, 6, f"Genere le {datetime.now().strftime('%Y-%m-%d %H:%M')}", new_x="LMARGIN", new_y="NEXT", align='C')
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


def send_daily_report_if_not_sent(recipient_emails=None):
    if recipient_emails is None:
        from config import DAILY_REPORT_RECIPIENTS
        recipient_emails = DAILY_REPORT_RECIPIENTS
    if isinstance(recipient_emails, str):
        recipient_emails = [recipient_emails]

    try:
        today_str = datetime.now().strftime('%Y-%m-%d')
        existing = query_one('''
            SELECT COUNT(*) as cnt FROM notification_logs
            WHERE notification_type = 'daily_report' AND DATE(sent_at) = ?
        ''', (today_str,))
        if existing and existing['cnt'] > 0:
            logger.info("Daily report already sent today. Skipping.")
            return False

        logger.info("Generating daily report...")
        products_output = _generate_products_report()
        products_pdf_output = _generate_products_pdf()
        movements_output = _generate_movements_report()
        movements_pdf_output = _generate_movements_pdf()

        subject = f"Rapport quotidien - {today_str}"
        body = f"Bonjour,\nVeuillez trouver ci-joint les rapports quotidiens pour la date du {today_str}.\nCordialement,\nLe Système de Gestion de Stock"

        for recipient_email in recipient_emails:
            try:
                msg = MIMEMultipart()
                msg['From'] = EMAIL_ADDRESS
                msg['To'] = recipient_email
                msg['Subject'] = subject
                msg.attach(MIMEText(body, 'plain', 'utf-8'))

                part_products = MIMEBase('application', 'vnd.openxmlformats-officedocument.spreadsheetml.sheet')
                part_products.set_payload(products_output.getvalue())
                encoders.encode_base64(part_products)
                part_products.add_header('Content-Disposition', 'attachment', filename=f"rapport_produits_{today_str}.xlsx")
                msg.attach(part_products)

                part_movements = MIMEBase('application', 'vnd.openxmlformats-officedocument.spreadsheetml.sheet')
                part_movements.set_payload(movements_output.getvalue())
                encoders.encode_base64(part_movements)
                part_movements.add_header('Content-Disposition', 'attachment', filename=f"rapport_mouvements_{today_str}.xlsx")
                msg.attach(part_movements)

                part_products_pdf = MIMEBase('application', 'pdf')
                part_products_pdf.set_payload(products_pdf_output.getvalue())
                encoders.encode_base64(part_products_pdf)
                part_products_pdf.add_header('Content-Disposition', 'attachment', filename=f"rapport_produits_{today_str}.pdf")
                msg.attach(part_products_pdf)

                part_movements_pdf = MIMEBase('application', 'pdf')
                part_movements_pdf.set_payload(movements_pdf_output.getvalue())
                encoders.encode_base64(part_movements_pdf)
                part_movements_pdf.add_header('Content-Disposition', 'attachment', filename=f"rapport_mouvements_{today_str}.pdf")
                msg.attach(part_movements_pdf)

                server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
                server.starttls()
                server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
                server.sendmail(EMAIL_ADDRESS, recipient_email, msg.as_string())
                server.quit()

                log_notification(recipient_email, 'daily_report', subject, "Rapport quotidien envoyé avec succès.")
                logger.info(f"Daily report sent to {recipient_email}")
            except Exception as e:
                logger.error(f"Failed to send daily report to {recipient_email}: {e}")
                try:
                    log_notification(recipient_email, 'daily_report', f"Échec d'envoi - {today_str}", str(e), status='failed')
                except Exception as log_e:
                    logger.error(f"Logging error: {log_e}")

        return True
    except Exception as e:
        logger.error(f"Failed to send daily report: {e}")
        return False


def check_expiring_products(days_threshold: int = 30) -> list:
    try:
        threshold_date = (datetime.now() + timedelta(days=days_threshold)).date()
        rows = query('''
            SELECT id, code, name, expiration_date
            FROM products
            WHERE deleted_at IS NULL AND expiration_date IS NOT NULL
            AND expiration_date <= ?
            AND expiration_date >= ?
            ORDER BY expiration_date ASC
        ''', (threshold_date.strftime('%Y-%m-%d'), datetime.now().date().strftime('%Y-%m-%d')))

        today = datetime.now().date()
        expiring = []
        for row in rows:
            exp_date = datetime.strptime(row['expiration_date'], '%Y-%m-%d').date()
            expiring.append({
                'id': row['id'], 'code': row['code'], 'name': row['name'],
                'expiration_date': row['expiration_date'],
                'days_until_expiry': (exp_date - today).days
            })
        return expiring
    except Exception as e:
        logger.error(f"Failed to check expiring products: {e}")
        return []


def check_low_stock():
    try:
        rows = query('''
            SELECT id, code, name, quantity, min_quantity
            FROM products
            WHERE deleted_at IS NULL AND min_quantity > 0 AND quantity < min_quantity
            ORDER BY (CAST(min_quantity AS REAL) - quantity) DESC
        ''')
        results = []
        for r in rows:
            results.append({
                'id': r['id'], 'code': r['code'], 'name': r['name'],
                'quantity': r['quantity'], 'min_quantity': r['min_quantity']
            })
            log_notification(
                'système@stock.local', 'low_stock',
                f"Alerte stock bas: {r['code']} - {r['name']}",
                f"Quantité: {r['quantity']}, Seuil: {r['min_quantity']}",
                r['id'], 'sent'
            )
        if results:
            logger.warning(f"Low stock alerts: {len(results)} products below threshold")
        return results
    except Exception as e:
        logger.error(f"Failed to check low stock: {e}")
        return []


def _load_template(path: str, variables: dict) -> Optional[str]:
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return f.read().format(**variables)
    except (FileNotFoundError, KeyError):
        return None


def _fallback_html(notification_type: str, product_info: dict, user: str) -> str:
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    return f"""<html><body style="font-family: Arial, sans-serif;"><div class="header" style="text-align:center;margin-bottom:20px;padding-bottom:20px;border-bottom:2px solid #dc3545;"><h2 style="color:#dc3545;">Produit supprimé du stock</h2></div><p><strong>Nom du produit:</strong> {product_info['name']}</p><p><strong>Code produit:</strong> {product_info['code']}</p><p><strong>Supprimé par:</strong> {user}</p><p><strong>Date de suppression:</strong> {now}</p><p>Ceci est une notification automatique du système de gestion de stock.</p></body></html>"""


def _generate_products_report() -> BytesIO:
    rows = query('SELECT * FROM products WHERE deleted_at IS NULL ORDER BY name')
    columns = [desc[1] for desc in query('PRAGMA table_info(products)')]
    french_headers = {
        'id': 'ID', 'code': 'Code Produit', 'name': 'Nom du Produit',
        'category': 'Catégorie', 'unit': 'Unité', 'quantity': 'Quantité',
        'brand': 'Marque', 'condition_status': 'État', 'chanter': 'Chantier',
        'storage_zone': 'Zone de Stockage', 'notes': 'Notes',
        'supplier_name': 'Nom Fournisseur', 'bc_number': 'Numéro BC',
        'bl_number': 'Numéro BL', 'n_facture': 'Numéro Facture',
        'type_achat': "Type d'Achat", 'expiration_date': "Date d'Expiration",
        'created_at': 'Créé le', 'updated_at': 'Mis à jour le',
        'image_path': 'Image', 'min_quantity': 'Quantité Min',
        'deleted_at': 'Supprimé le', 'workshop_id': 'Atelier',
        'created_by': 'Créé par'
    }
    output = BytesIO()
    workbook = xlsxwriter.Workbook(output)
    worksheet = workbook.add_worksheet('Produits')
    header_fmt = workbook.add_format({'bold': True, 'bg_color': '#D3D3D3', 'border': 1})
    data_fmt = workbook.add_format({'border': 1})
    headers = [french_headers.get(col, col) for col in columns]
    for col, h in enumerate(headers):
        worksheet.write(0, col, h, header_fmt)
    for r_idx, row in enumerate(rows, 1):
        for c_idx, val in enumerate(row):
            worksheet.write(r_idx, c_idx, val, data_fmt)
    for col in range(len(headers)):
        worksheet.set_column(col, col, 18)
    workbook.close()
    output.seek(0)
    return output


def _generate_movements_report() -> BytesIO:
    rows = query('''
        SELECT sm.created_at, sm.movement_type, p.code, p.name, p.category, sm.quantity,
               sm.notes, u.username, sm.supplier_name, sm.bc_number, sm.bl_number,
               sm.n_facture, sm.type_achat, sm.chantier_exp_recep, sm.nom_donneur_ordre,
               sm.nom_magasinier, sm.nom_chauffeur, sm.matricule
        FROM stock_movements sm
        JOIN products p ON sm.product_id = p.id
        JOIN users u ON sm.user_id = u.id
        ORDER BY sm.created_at DESC
    ''')
    headers = [
        'Date', 'Type de Mouvement', 'Code Produit', 'Nom du Produit', 'Catégorie', 'Quantité',
        'Notes', 'Utilisateur', 'Nom Fournisseur', 'Numéro BC', 'Numéro BL',
        'Numéro Facture', "Type d'Achat", 'Chantier/Exp/Récep', "Donneur d'ordre",
        'Magasinier', 'Chauffeur', 'Matricule'
    ]
    output = BytesIO()
    workbook = xlsxwriter.Workbook(output)
    worksheet = workbook.add_worksheet('Mouvements')
    header_fmt = workbook.add_format({'bold': True, 'bg_color': '#D3D3D3', 'border': 1})
    data_fmt = workbook.add_format({'border': 1})
    for col, h in enumerate(headers):
        worksheet.write(0, col, h, header_fmt)
    for r_idx, row in enumerate(rows, 1):
        for c_idx, val in enumerate(row):
            worksheet.write(r_idx, c_idx, val, data_fmt)
    for col in range(len(headers)):
        worksheet.set_column(col, col, 18)
    workbook.close()
    output.seek(0)
    return output
