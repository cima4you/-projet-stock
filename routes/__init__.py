from .auth import register_auth_routes
from .dashboard import register_dashboard_routes
from .products import register_product_routes
from .movements import register_movement_routes
from .users import register_user_routes
from .email_mgmt import register_email_routes
from .logo import register_logo_routes
from .reports import register_report_routes
from .categories import register_category_routes
from .suppliers import register_supplier_routes
from .notifications_api import register_notifications_api_routes
from .inventory import register_inventory_routes
from .search import register_search_routes
from .workshops import register_workshop_routes
from .cron import register_cron_routes
from .settings import register_settings_routes


def register_blueprints(app):
    register_auth_routes(app)
    register_dashboard_routes(app)
    register_product_routes(app)
    register_movement_routes(app)
    register_user_routes(app)
    register_email_routes(app)
    register_logo_routes(app)
    register_report_routes(app)
    register_category_routes(app)
    register_supplier_routes(app)
    register_notifications_api_routes(app)
    register_inventory_routes(app)
    register_search_routes(app)
    register_workshop_routes(app)
    register_cron_routes(app)
    register_settings_routes(app)
