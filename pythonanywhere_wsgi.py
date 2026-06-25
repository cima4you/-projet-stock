import sys
import os

path = os.path.expanduser('~/projet_stock')
if path not in sys.path:
    sys.path.insert(0, path)

from main import app

application = app
