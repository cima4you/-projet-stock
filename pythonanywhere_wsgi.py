import sys
import os

path = os.path.expanduser('~/projet_stock')
if path not in sys.path:
    sys.path.insert(0, path)

# Load .env if present (for PythonAnywhere env vars)
env_path = os.path.join(path, '.env')
if os.path.exists(env_path):
    from dotenv import load_dotenv
    load_dotenv(env_path)

from main import app

application = app
