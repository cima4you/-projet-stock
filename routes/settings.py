import logging
from flask import render_template, request, redirect, url_for, session, flash
from utils import admin_required, get_app_setting, set_app_setting, auto_archive_inactive_products
from config import AUTO_ARCHIVE_INACTIVE_MONTHS
from translations import TRANSLATIONS

logger = logging.getLogger(__name__)


def register_settings_routes(app):

    @app.route('/auto_archive', methods=['GET', 'POST'])
    @admin_required
    def auto_archive():
        if request.method == 'POST':
            action = request.form.get('action', '')
            if action == 'save':
                try:
                    months = int(request.form.get('months', AUTO_ARCHIVE_INACTIVE_MONTHS))
                    if months < 1:
                        months = 1
                    set_app_setting('auto_archive_months', months)
                    flash(f"Paramètre enregistré : archiver les produits inactifs depuis {months} mois", 'success')
                except (ValueError, TypeError):
                    flash("Valeur invalide pour le nombre de mois", 'error')
                return redirect(url_for('auto_archive'))
            elif action == 'run':
                try:
                    months = int(request.form.get('months', get_app_setting('auto_archive_months', str(AUTO_ARCHIVE_INACTIVE_MONTHS))))
                    archived = auto_archive_inactive_products(months=months)
                    if archived:
                        flash(f"{len(archived)} produit(s) inactif(s) archivé(s) : " + ", ".join(f"{c} - {n}" for c, n in archived[:20]), 'success')
                    else:
                        flash("Aucun produit inactif à archiver", 'info')
                except Exception as e:
                    logger.error(f"Auto-archive error: {e}")
                    flash(f"Erreur lors de l'archivage : {str(e)}", 'error')
                return redirect(url_for('auto_archive'))

        months = int(get_app_setting('auto_archive_months', str(AUTO_ARCHIVE_INACTIVE_MONTHS)))
        return render_template('auto_archive.html', months=months,
                             translations=TRANSLATIONS[session.get('lang', 'fr')],
                             lang=session.get('lang', 'fr'))
