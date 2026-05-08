# celery_worker.py
import os
from app import create_app, celery

# Buat aplikasi Flask untuk konteks Celery
app = create_app(os.getenv('FLASK_ENV', 'development'))