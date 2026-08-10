# Agents Instructions

## Project Overview

Système de Gestion de Stock (Stock Management System) - a French-language Flask web application for inventory management. (Interface et notifications en français uniquement.)

## Tech Stack

- **Backend:** Python 3.11+, Flask 3.1
- **Database:** SQLite (via Flask-SQLAlchemy)
- **Frontend:** Bootstrap 5, Font Awesome 6, Jinja2 templates
- **Package Manager:** uv
- **Production Server:** gunicorn

## Key Commands

- **Run app:** `python main.py` (starts on port 8050)
- **Install deps:** `uv sync` or `pip install -r requirements.txt`
- **Encrypt .env:** `python protect_env.py`
- **Database:** SQLite file `stock.db`

## Multi-Workshop Architecture

**Key pattern:** Every route that reads/writes stock data uses `workshop_filter()` from `utils.py` to scope queries by the logged-in user's workshop. Admins see all workshops unless they have a specific `workshop_id` in session.

Flow:
1. `routes/auth.py` stores `workshop_id` + `workshop_name` in `session` on login
2. All data routes call `workshop_filter()` to append `AND workshop_id = ?` to SQL queries
3. Notification functions filter recipients by `workshop_id` parameter

**Important index notes for `SELECT * FROM users`:**
After ALTER TABLE workshop_id was added as the last column, column indices are:
- `user[1]` = username, `user[3]` = email, `user[4]` = role, `user[5]` = active, `user[10]` = workshop_id

## Project Structure

| Path | Purpose |
|---|---|
| `routes/` | Flask blueprints (auth, dashboard, products, movements, users, categories, suppliers, reports, inventory, workshops, etc.) |
| `templates/` | Jinja2 HTML templates |
| `static/` | CSS, JS, uploaded logos/images |
| `email_templates/` | HTML email templates (French) |
| `main.py` | App entry point |
| `config.py` | Configuration (SMTP, paths, etc.) |
| `db.py` | SQLite database setup & queries (includes `workshops` table + migration) |
| `utils.py` | Utility functions, decorators, `workshop_filter()` helper |
| `notifications.py` | Email & WhatsApp notifications (scoped by workshop_id) |
| `csrf.py` | CSRF protection |
| `translations.py` | French labels (legacy Arabic/French translations, interface French-only) |

## Routes (Blueprints)

Each blueprint is registered in `routes/__init__.py`. Main routes:

- `/auth` - Login/logout/password reset
- `/dashboard` - Dashboard with stats
- `/products` - Product CRUD
- `/movements` - Stock movements (in/out/transfer)
- `/users` - User management
- `/categories` - Category management
- `/suppliers` - Supplier management
- `/reports` - PDF/Excel report generation
- `/audit_log` - Audit log (admin-only, before/after changes + login history)
- `/inventory` - Physical inventory counting
- `/email` - Email configuration
- `/notifications` - WhatsApp notifications
- `/search` - Search functionality
- `/workshops` - Workshop management (CRUD)
- `/workshop_dashboard/<id>` - Per-workshop dashboard (admin only)
- `/workshop_comparison` - Workshop comparison page (admin only)

## Database

- SQLite (`stock.db`)
- Key models: User, Product, Category, Supplier, Movement, Inventory, AuditLog
- Email configuration stored in `email_config.json`

## Authentication & Authorization

- Roles: `user`, `admin`, `principal_admin`
- Default admin: `admin` / `bj319260`
- Password hashing via Werkzeug
- CSRF protection enabled

## Notifications

- **WhatsApp:** Supports UltraMsg and CallMeBot APIs
- **Email:** SMTP-based (configurable via UI)

## Conventions

- **Language:** French only (interface, emails, reports). Legacy Arabic translations still in `translations.py` but unused.
- **Quantities:** Decimal quantities supported (REAL), formatted with 2 decimals in templates.
- **Templates:** Extend `base.html`, use Bootstrap 5 classes
- **Forms:** Flask-WTF with CSRF
- **CSS:** Custom styles in `static/css/style.css`
- **JS:** Custom scripts in `static/js/main.js`
- **Routes:** Organized by feature in `routes/` as Flask blueprints

## Lint & Type Check

No specific lint/type-check commands configured. Format Python code with `ruff` or `black` if available.

## Deployment (Render)

- **`render.yaml`** - Blueprint config for Render (web service + PostgreSQL database)
- **`requirements.txt`** - Dependencies for Render build
- **Database:** Auto-detects PostgreSQL via `DATABASE_URL` env var. Falls back to SQLite locally.
- **Start command:** `gunicorn main:app --bind 0.0.0.0:$PORT --workers 2`

### Deploy steps:
1. Push to GitHub
2. Go to [dashboard.render.com](https://dashboard.render.com) → New → Blueprint
3. Connect your repository
4. Render reads `render.yaml` and creates Web Service + PostgreSQL automatically
