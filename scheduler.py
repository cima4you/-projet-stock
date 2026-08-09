import logging
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler

logger = logging.getLogger(__name__)
scheduler = BackgroundScheduler()


def check_expiry_job():
    from notifications import check_expiring_products, send_expiring_products_notification
    logger.info(f"APScheduler: Checking expiring products at {datetime.now()}")
    try:
        for days in [7, 15, 30]:
            expiring = check_expiring_products(days_threshold=days)
            if expiring:
                logger.info(f"Found {len(expiring)} products expiring within {days} days")
                send_expiring_products_notification(expiring, lang='fr')
    except Exception as e:
        logger.error(f"APScheduler expiry check error: {e}")


def daily_report_job():
    from notifications import send_daily_report_if_not_sent
    logger.info(f"APScheduler: Sending daily report at {datetime.now()}")
    try:
        send_daily_report_if_not_sent()
    except Exception as e:
        logger.error(f"APScheduler daily report error: {e}")


def check_low_stock_job():
    from notifications import check_low_stock
    logger.info(f"APScheduler: Checking low stock at {datetime.now()}")
    try:
        check_low_stock()
    except Exception as e:
        logger.error(f"APScheduler low stock check error: {e}")


def auto_archive_job():
    from utils import auto_archive_inactive_products
    logger.info(f"APScheduler: Auto-archiving inactive products at {datetime.now()}")
    try:
        archived = auto_archive_inactive_products()
        if archived:
            logger.info(f"Auto-archived {len(archived)} inactive products: {[c for c, _ in archived]}")
        else:
            logger.info("Auto-archive: no inactive products to archive")
    except Exception as e:
        logger.error(f"APScheduler auto-archive error: {e}")


def start_scheduler():
    from notifications import check_expiring_products, send_expiring_products_notification, send_daily_report_if_not_sent

    scheduler.add_job(check_expiry_job, 'interval', hours=6, id='check_expiry', replace_existing=True)
    scheduler.add_job(daily_report_job, 'interval', hours=24, id='daily_report', replace_existing=True)
    scheduler.add_job(check_low_stock_job, 'interval', hours=6, id='check_low_stock', replace_existing=True)
    scheduler.add_job(auto_archive_job, 'interval', hours=24, id='auto_archive', replace_existing=True)

    scheduler.start()
    logger.info("APScheduler started successfully (expiry: 6h, report: 24h, low stock: 6h, auto-archive: 24h)")

    try:
        logger.info("Sending daily report on startup...")
        send_daily_report_if_not_sent()
    except Exception as e:
        logger.error(f"Startup daily report error: {e}")
