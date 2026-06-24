import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.chdir(BASE)
sys.path.insert(0, BASE)

from serverless_wsgi import handle_request
from main import app as application


def handler(event, context):
    return handle_request(application, event, context)
