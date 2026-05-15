# app/__init__.py
import os
import sys
from flask import Flask
from app.config import config_by_name
from app.extensions import db, jwt, cors, celery, migrate

def create_app(config_name='development'):
    app = Flask(__name__)
    app.config.from_object(config_by_name[config_name])

    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    @jwt.user_lookup_loader
    def user_lookup_callback(_jwt_header, jwt_data):
        identity = jwt_data["sub"]
        from app.models import User
        return User.query.filter_by(Id_User=int(identity)).one_or_none()

    cors.init_app(app, origins=app.config['CORS_ORIGINS'])

    # Hanya inisialisasi Celery jika TIDAK menjalankan perintah migrasi
    # dan tidak sedang menjalankan flask shell (opsional)
    # if not any(cmd in sys.argv for cmd in ['db', 'shell']):
    #     from app.tasks.training_tasks import make_celery, register_train_task
    #     global celery
    #     celery = make_celery(app)
    #     register_train_task(celery, app)

    # Register blueprints
    from app.api.auth import auth_bp
    from app.api.admin import admin_bp
    from app.api.mahasiswa import mahasiswa_bp
    from app.api.dosen import dosen_bp

    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(admin_bp, url_prefix='/api/admin')
    app.register_blueprint(mahasiswa_bp, url_prefix='/api/mahasiswa')
    app.register_blueprint(dosen_bp, url_prefix='/api/dosen')

    # Hanya load model jika bukan migrasi
    if not any(cmd in sys.argv for cmd in ['db', 'shell']):
        with app.app_context():
            from app.ml.predictor import registry
            try:
                registry.reload_from_db(app)
            except Exception as e:
                app.logger.warning(f"Gagal memuat model ML: {e} (mungkin tabel models belum ada)")

    return app