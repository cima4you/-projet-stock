import os
import sys
import getpass
from dotenv import load_dotenv

ENCRYPTED_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_FILE = os.path.join(ENCRYPTED_DIR, '.env')
ENCRYPTED_FILE = os.path.join(ENCRYPTED_DIR, '.env.encrypted')
SALT_FILE = os.path.join(ENCRYPTED_DIR, '.env.salt')

# Load .env normally if it exists (plain text mode)
if os.path.exists(ENV_FILE):
    load_dotenv(ENV_FILE)
    ENV_MODE = "plain"

# Otherwise, try loading encrypted .env.encrypted
elif os.path.exists(ENCRYPTED_FILE) and os.path.exists(SALT_FILE):
    password = os.environ.get('ENV_PASSWORD')  # try system env variable first
    if not password:
        password = getpass.getpass("[KEY] Enter password to decrypt .env: ")

    try:
        from protect_env import decrypt_to_memory
        env_vars = decrypt_to_memory(password)
        if not env_vars:
            print("[ERROR] Wrong password. Variables not loaded.", file=sys.stderr)
            ENV_MODE = "encrypted_failed"
        else:
            for k, v in env_vars.items():
                os.environ[k] = v
            ENV_MODE = "encrypted"
            print("[OK] Decrypted .env.encrypted successfully")
    except ImportError:
        print("[WARN] cryptography library not installed. Run: pip install cryptography", file=sys.stderr)
        ENV_MODE = "encrypted_failed"
else:
    ENV_MODE = "none"

# Email Configuration
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
EMAIL_ADDRESS = os.environ.get('EMAIL_ADDRESS')
EMAIL_PASSWORD = os.environ.get('EMAIL_PASSWORD')
NOTIFICATION_EMAIL = os.environ.get('NOTIFICATION_EMAIL', EMAIL_ADDRESS)

# Session
SESSION_SECRET = os.environ.get("SESSION_SECRET", "fallback_secret_key_change_in_production")

# Default admin credentials (override in .env)
DEFAULT_ADMIN_USERNAME = os.environ.get('DEFAULT_ADMIN_USERNAME', 'admin')
DEFAULT_ADMIN_PASSWORD = os.environ.get('DEFAULT_ADMIN_PASSWORD', 'bj319260')
DEFAULT_ADMIN_EMAIL = os.environ.get('DEFAULT_ADMIN_EMAIL', 'bazigherachid@gmail.com')

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "stock.db")
DATABASE_URL = os.environ.get('DATABASE_URL', '')
IS_POSTGRES = DATABASE_URL.startswith('postgresql')
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
LOGO_FOLDER = os.path.join(BASE_DIR, 'static', 'logos')
# File upload
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'xlsx', 'xls'}
LOGO_EXTENSIONS = {'png', 'jpg', 'jpeg'}
MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB

# Cron secret for external cron jobs (cron-job.org, etc.)
CRON_SECRET = os.environ.get('CRON_SECRET', 'change_this_in_production')

# Daily report recipients
DAILY_REPORT_RECIPIENTS = [
    email.strip() for email in os.environ.get(
        'DAILY_REPORT_RECIPIENTS',
        'bazigherachid@gmail.com'
    ).split(',') if email.strip()
]
