import os
import webbrowser
import logging
from flask import Flask, session, request
from flask_moment import Moment
from config import (SESSION_SECRET, UPLOAD_FOLDER, LOGO_FOLDER, MAX_CONTENT_LENGTH,
                    DB_PATH, FLASK_DEBUG, ENABLE_SECURE_COOKIE)
from db import init_database

logging.basicConfig(level=logging.DEBUG if FLASK_DEBUG else logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = SESSION_SECRET
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = ENABLE_SECURE_COOKIE
moment = Moment(app)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['LOGO_FOLDER'] = LOGO_FOLDER
app.config['MAX_CONTENT_LENGTH'] = MAX_CONTENT_LENGTH

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(LOGO_FOLDER, exist_ok=True)
os.makedirs('email_templates', exist_ok=True)
os.makedirs('static/css', exist_ok=True)
os.makedirs('static/js', exist_ok=True)
os.makedirs('static/images', exist_ok=True)
os.makedirs('static/logos', exist_ok=True)
os.makedirs('templates', exist_ok=True)

init_database()

from csrf import init_csrf
app.config['WTF_CSRF_ENABLED'] = False
init_csrf(app)


@app.before_request
def force_french():
    if session.get('lang') != 'fr':
        session['lang'] = 'fr'


@app.after_request
def add_security_headers(resp):
    resp.headers.setdefault('X-Content-Type-Options', 'nosniff')
    resp.headers.setdefault('X-Frame-Options', 'SAMEORIGIN')
    resp.headers.setdefault('Referrer-Policy', 'same-origin')
    resp.headers.setdefault('Permissions-Policy', 'camera=(), microphone=(), geolocation=()')
    if ENABLE_SECURE_COOKIE:
        resp.headers.setdefault('Strict-Transport-Security', 'max-age=31536000; includeSubDomains')
    return resp


@app.after_request
def no_store_for_sensitive(resp):
    if request.path.startswith('/login') or request.path.startswith('/dashboard'):
        resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    return resp


@app.template_filter('num')
def format_number(value):
    if value is None or value == '':
        return ''
    try:
        f = float(value)
        if f.is_integer():
            return str(int(f))
        return f'{f:g}'
    except (TypeError, ValueError):
        return str(value)

from routes import register_blueprints
register_blueprints(app)

try:
    from scheduler import start_scheduler
    start_scheduler()
    logger.info("Scheduler started")
except Exception as e:
    logger.warning(f"Could not start scheduler: {e}")

if __name__ == '__main__':
    if FLASK_DEBUG:
        webbrowser.open('http://127.0.0.1:8050')
    app.run(host='0.0.0.0', port=8050, debug=FLASK_DEBUG)
