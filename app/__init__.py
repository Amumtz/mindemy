# app/__init__.py
import os
import sys
from flask import Flask
from flask_cors import CORS
from app.config import config_by_name
from app.extensions import db, jwt, cors, celery, migrate

def create_app(config_name='development'):
    app = Flask(__name__)
    app.config.from_object(config_by_name[config_name])

    if config_name == 'production' and not app.config.get('SQLALCHEMY_DATABASE_URI'):
        raise ValueError("DATABASE_URL environment variable is not set for production")

    db.init_app(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    @jwt.user_lookup_loader
    def user_lookup_callback(_jwt_header, jwt_data):
        identity = jwt_data["sub"]
        from app.models import User
        return User.query.filter_by(Id_User=int(identity)).one_or_none()

    cors.init_app(app, origins=app.config['CORS_ORIGINS'])

    # Register blueprints
    from app.api.auth import auth_bp
    from app.api.admin import admin_bp
    from app.api.mahasiswa import mahasiswa_bp
    from app.api.dosen import dosen_bp
    from app.api.kuesioner import kuesioner_bp  # ← TAMBAHKAN

    app.register_blueprint(auth_bp, url_prefix='/api/auth')
    app.register_blueprint(admin_bp, url_prefix='/api/admin')
    app.register_blueprint(mahasiswa_bp, url_prefix='/api/mahasiswa')
    app.register_blueprint(dosen_bp, url_prefix='/api/dosen')
    app.register_blueprint(kuesioner_bp, url_prefix='/api/kuesioner')  # ← TAMBAHKAN

    CORS(app, 
         supports_credentials=True,
         origins=["http://localhost:5173", "http://localhost:3000"],  # ganti dengan origin frontend
         allow_headers=["Content-Type", "Authorization"],
         methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])
    
    # Hanya load model jika bukan migrasi
    if not any(cmd in sys.argv for cmd in ['db', 'shell']):
        with app.app_context():
            from app.ml.predictor import registry
            try:
                registry.reload_from_db(app)
            except Exception as e:
                app.logger.warning(f"Gagal memuat model ML: {e} (mungkin tabel models belum ada)")

    return app

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['MODELS_FOLDER'], exist_ok=True)
os.makedirs(app.config['PROFILE_PHOTO_FOLDER'], exist_ok=True)
