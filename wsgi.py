# PythonAnywhere WSGI template: paste into /var/www/<username>_pythonanywhere_com_wsgi.py
# and change PROJECT_DIR to your project path.
import sys, os
PROJECT_DIR = os.path.expanduser('~/clora_and_co')
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
os.environ.setdefault('SECRET_KEY', 'put-a-long-random-string-here')
from app import app as application  # noqa
