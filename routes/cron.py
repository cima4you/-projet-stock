import logging
from flask import request, jsonify
from config import CRON_SECRET
from notifications import send_daily_report_if_not_sent

logger = logging.getLogger(__name__)


def register_cron_routes(app):

    @app.route('/cron/daily-report')
    def cron_daily_report():
        token = request.args.get('token')
        if not token or token != CRON_SECRET:
            return jsonify({'error': 'Unauthorized'}), 401

        try:
            sent = send_daily_report_if_not_sent()
            if sent:
                return jsonify({'status': 'ok', 'message': 'Report sent'}), 200
            else:
                return jsonify({'status': 'skipped', 'message': 'Already sent today'}), 200
        except Exception as e:
            logger.error(f"Cron daily report error: {e}")
            return jsonify({'status': 'error', 'message': str(e)}), 500
