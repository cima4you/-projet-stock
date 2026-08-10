import logging
from flask import render_template, request, redirect, url_for, session, flash
from db import get_db, execute, query, query_one
from utils import admin_required, get_translation, workshop_filter
from notifications import send_email, check_expiring_products, send_expiring_products_notification
from translations import TRANSLATIONS
from config import SMTP_SERVER, EMAIL_ADDRESS, NOTIFICATION_EMAIL

logger = logging.getLogger(__name__)


def register_email_routes(app):

    @app.route('/email_management')
    @admin_required
    def email_management():
        email_status = "Configuré" if EMAIL_ADDRESS else "Non configuré"
        workshops = query('SELECT id, name, city FROM workshops WHERE active = 1 ORDER BY name')
        filter_ws = request.args.get('workshop_id', '')
        try:
            filter_val = int(filter_ws) if filter_ws else None
        except ValueError:
            filter_val = None
        recipients = []
        ws_filter_sql = ' AND nr.workshop_id = ?' if filter_val else ''
        ws_params = (filter_val,) if filter_val else ()
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(f'''
                SELECT nr.id, nr.name, nr.active, nr.workshop_id, COALESCE(w.name, '') as workshop_name
                FROM notification_recipients nr
                LEFT JOIN workshops w ON nr.workshop_id = w.id{ws_filter_sql}
                ORDER BY nr.name
            ''', ws_params)
            for r in cursor.fetchall():
                cursor.execute('''
                    SELECT id, email, active, notify_achat_par_bc, notify_achat_par_caisse,
                           notify_achat_a_regulariser, notify_transfert, notify_product_deletion,
                           notify_product_expiration, notify_consumption
                    FROM recipient_emails
                    WHERE recipient_id = ? ORDER BY email
                ''', (r[0],))
                recipients.append({'id': r[0], 'name': r[1], 'active': r[2], 'workshop_id': r[3], 'workshop_name': r[4], 'emails': cursor.fetchall()})
        return render_template('email_management.html', email_status=email_status,
                             smtp_server=SMTP_SERVER, email_address=EMAIL_ADDRESS,
                             recipients=recipients, workshops=workshops,
                             filter_workshop=filter_val,
                             translations=TRANSLATIONS[session.get('lang', 'fr')],
                             lang=session.get('lang', 'fr'))

    @app.route('/test_email')
    @admin_required
    def test_email():
        try:
            test_email = NOTIFICATION_EMAIL or EMAIL_ADDRESS
            if not test_email:
                flash("Aucune adresse email configurée pour le test", 'error')
                return redirect(url_for('email_management'))
            from datetime import datetime
            subject = "Test de connexion email - Système de gestion de stock"
            body = f"Ceci est un email de test.\nHeure: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            success = send_email(test_email, subject, body)
            flash("Email de test envoyé avec succès" if success else "Échec de l'envoi", 'success' if success else 'error')
        except Exception as e:
            logger.error(f"Error testing email: {e}")
            flash(f"Erreur: {str(e)}", 'error')
        return redirect(url_for('email_management'))

    def _parse_notification_form(form):
        return (
            1 if 'notify_achat_par_bc' in form else 0,
            1 if 'notify_achat_par_caisse' in form else 0,
            1 if 'notify_achat_a_regulariser' in form else 0,
            1 if 'notify_transfert' in form else 0,
            1 if 'notify_consumption' in form else 0,
            1 if 'notify_product_deletion' in form else 0,
            1 if 'notify_product_expiration' in form else 0,
        )

    @app.route('/add_recipient', methods=['POST'])
    @admin_required
    def add_recipient():
        try:
            name = request.form['name'].strip()
            workshop_id = request.form.get('workshop_id', '') or None
            if workshop_id:
                workshop_id = int(workshop_id)

            emails = request.form.getlist('email[]')
            if not emails or not any(e.strip() for e in emails):
                flash("Veuillez ajouter au moins un email.", 'error')
                return redirect(url_for('email_management'))

            recipient_id = execute('''
                INSERT INTO notification_recipients (name, email, workshop_id)
                VALUES (?, ?, ?)
            ''', (name, 'placeholder@local', workshop_id))

            notify_bc, notify_caisse, notify_reg, notify_transfert, \
                notify_consumption, notify_del, notify_exp = _parse_notification_form(request.form)

            for email in emails:
                email = email.strip()
                if email:
                    execute('''
                        INSERT INTO recipient_emails
                        (recipient_id, email, active, notify_achat_par_bc, notify_achat_par_caisse,
                         notify_achat_a_regulariser, notify_transfert, notify_consumption,
                         notify_product_deletion, notify_product_expiration)
                        VALUES (?, ?, 1, ?, ?, ?, ?, ?, ?, ?)
                    ''', (recipient_id, email, notify_bc, notify_caisse, notify_reg,
                          notify_transfert, notify_consumption, notify_del, notify_exp))
            flash(get_translation('recipient_added_successfully'), 'success')
        except Exception as e:
            logger.error(f"Error adding recipient: {e}")
            flash(f"Erreur: {str(e)}", 'error')
        return redirect(url_for('email_management'))

    @app.route('/edit_recipient/<int:recipient_id>', methods=['POST'])
    @admin_required
    def edit_recipient(recipient_id):
        try:
            name = request.form['name'].strip()
            workshop_id = request.form.get('workshop_id', '') or None
            if workshop_id:
                workshop_id = int(workshop_id)

            execute('UPDATE notification_recipients SET name=?, workshop_id=? WHERE id=?',
                    (name, workshop_id, recipient_id))

            email_ids = request.form.getlist('email_id[]')
            emails = request.form.getlist('email[]')
            email_active = request.form.getlist('email_active[]')

            for i in range(len(emails)):
                eid = int(email_ids[i]) if i < len(email_ids) else 0
                email = emails[i].strip()
                if not email:
                    continue
                active = 1 if (i < len(email_active) and email_active[i] == '1') else 1
                fields = _parse_notification_form(request.form)
                suffix = f"_{eid}" if eid else ""
                notify_bc = 1 if f'notify_achat_par_bc{suffix}' in request.form else 0
                notify_caisse = 1 if f'notify_achat_par_caisse{suffix}' in request.form else 0
                notify_reg = 1 if f'notify_achat_a_regulariser{suffix}' in request.form else 0
                notify_transfert = 1 if f'notify_transfert{suffix}' in request.form else 0
                notify_consumption = 1 if f'notify_consumption{suffix}' in request.form else 0
                notify_del = 1 if f'notify_product_deletion{suffix}' in request.form else 0
                notify_exp = 1 if f'notify_product_expiration{suffix}' in request.form else 0

                if eid:
                    execute('''
                        UPDATE recipient_emails
                        SET email=?, active=?, notify_achat_par_bc=?, notify_achat_par_caisse=?,
                            notify_achat_a_regulariser=?, notify_transfert=?, notify_consumption=?,
                            notify_product_deletion=?, notify_product_expiration=?
                        WHERE id=?
                    ''', (email, active, notify_bc, notify_caisse, notify_reg,
                          notify_transfert, notify_consumption, notify_del, notify_exp, eid))
                else:
                    execute('''
                        INSERT INTO recipient_emails
                        (recipient_id, email, active, notify_achat_par_bc, notify_achat_par_caisse,
                         notify_achat_a_regulariser, notify_transfert, notify_consumption,
                         notify_product_deletion, notify_product_expiration)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (recipient_id, email, active, notify_bc, notify_caisse, notify_reg,
                          notify_transfert, notify_consumption, notify_del, notify_exp))
            flash("Destinataire mis à jour avec succès", 'success')
        except Exception as e:
            logger.error(f"Error updating recipient: {e}")
            flash(f"Erreur: {str(e)}", 'error')
        return redirect(url_for('email_management'))

    @app.route('/delete_email/<int:email_id>')
    @admin_required
    def delete_email(email_id):
        try:
            execute('DELETE FROM recipient_emails WHERE id = ?', (email_id,))
            flash("Email supprimé avec succès", 'success')
        except Exception as e:
            logger.error(f"Error deleting email: {e}")
            flash(f"Erreur: {str(e)}", 'error')
        return redirect(url_for('email_management'))

    @app.route('/check_expiring_products_manual')
    @admin_required
    def check_expiring_products_manual():
        try:
            expiring = check_expiring_products(30)
            if expiring:
                send_expiring_products_notification(expiring, session.get('lang', 'fr'), workshop_id=session.get('workshop_id'))
                flash(f"Vérification terminée. {len(expiring)} produits expirent bientôt.", 'info')
            else:
                flash("Aucun produit n'expire dans les 30 prochains jours.", 'info')
        except Exception as e:
            logger.error(f"Error: {e}")
            flash(f"Erreur: {str(e)}", 'error')
        return redirect(url_for('email_management'))
