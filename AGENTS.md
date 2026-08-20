# Agents Instructions

## Project Overview

Système de Gestion de Stock (Stock Management System) - a French-language Flask web application for inventory management. (Interface et notifications en français uniquement.)

## Tech Stack

- **Backend:** Python 3.11+, Flask 3.1
- **Database:** SQLite (raw `sqlite3` via `db.py`, auto-switches to PostgreSQL via `DATABASE_URL`)
- **Frontend:** Bootstrap 5, Font Awesome 6, Jinja2 templates
- **Package Manager:** uv
- **Production Server:** gunicorn (Render) / WSGI (PythonAnywhere)

## Key Commands

- **Run app:** `python main.py` (starts on port 8050)
- **Install deps:** `uv sync` or `pip install -r requirements.txt`
- **Encrypt .env:** `python protect_env.py encrypt` (→ `.env.encrypted` + `.env.salt`); `decrypt`/`unlock` to restore/test
- **Database:** SQLite file `stock.db`

## Multi-Workshop Architecture

**Key pattern:** Every route that reads/writes stock data uses `workshop_filter()` from `utils.py` to scope queries by the logged-in user's workshop. Admins see all workshops unless they have a specific `workshop_id` in session.

Flow:
1. `routes/auth.py` stores `workshop_id` + `workshop_name` in `session` on login
2. All data routes call `workshop_filter()` to append `AND workshop_id = ?` to SQL queries
3. Notification functions filter recipients by `workshop_id` parameter

**Important index notes for `SELECT * FROM users` (legacy, being phased out):**
If code still uses `SELECT *` + positional indexes, after ALTER TABLE workshop_id was added as the last column:
- `user[1]` = username, `user[3]` = email, `user[4]` = role, `user[5]` = active, `user[10]` = workshop_id
**Prefer explicit column lists + named access (row factory) in new code.**

## Security Hardening (applied 2026-08)

- **CSRF on all destructive actions:** delete/restore routes are `POST`-only (`delete_category`, `delete_email`, `delete_movement`, `delete_product`, `restore_product`, `delete_supplier`, `delete_user`, `delete_workshop`). GET requests return 405.
- **Mandatory secrets:** `SESSION_SECRET` and `CRON_SECRET` have NO fallback — `config.py` raises `RuntimeError` at startup if missing from `.env`.
- **Debug off by default:** `main.py` uses `FLASK_DEBUG=1` env var only (production-safe otherwise).
- **Active-user check:** `login_required`/`admin_required`/`principal_admin_required` re-read `role, active` from DB on every request; deactivated users are logged out immediately.
- **IP-based login lockout:** `login_attempts` table — 5 failures / 5 min per IP (no longer client-side session cookie).
- **Hashed reset tokens:** `reset_token` stored as SHA-256; email carries the plain token.
- **Password policy:** min 8 chars + letters + digit + special char (shared `validate_password_strength()` in `utils.py`).
- **Security headers:** `X-Frame-Options: SAMEORIGIN`, `X-Content-Type-Options: nosniff`, `Referrer-Policy`, `Permissions-Policy`, plus HSTS when `SECURE_COOKIE=1`. Session cookie `HttpOnly` + `SameSite=Lax`.
- **Excel upload validation:** `validate_excel_content()` checks file magic bytes (`PK`/OLE2), not just extension.
- **`.env` encryption:** `python protect_env.py encrypt` → `.env.encrypted` + `.env.salt`; delete plain `.env` afterwards. `config.py` auto-loads encrypted file (needs `ENV_PASSWORD` env var or prompt).

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
- Default admin: created from `DEFAULT_ADMIN_USERNAME`/`DEFAULT_ADMIN_PASSWORD` env vars (see `config.py`); change the password after first login
- Password hashing via Werkzeug
- CSRF protection enabled (`csrf.py`, `init_csrf(app)`)
- **Login lockout:** 5 failed attempts / 5 min per IP (table `login_attempts`)
- **Password policy:** min 8 chars + letter + digit + special char

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
