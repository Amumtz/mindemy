# passenger_wsgi.py
import sys
import os

# Tambahkan path project ke sys.path
sys.path.insert(0, os.path.dirname(__file__))

from app import create_app

# Gunakan environment 'production'
application = create_app('production')