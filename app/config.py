# app/config.py

import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()  # load .env file

class BaseConfig:
    SECRET_KEY        = os.getenv("SECRET_KEY", "change-me-in-production")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    JWT_SECRET_KEY           = os.getenv("JWT_SECRET_KEY", "jwt-secret-change-me")
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(hours=int(os.getenv("JWT_ACCESS_HOURS", 8)))
    JWT_REFRESH_TOKEN_EXPIRES = timedelta(days=int(os.getenv("JWT_REFRESH_DAYS", 30)))

    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")

    CELERY_BROKER_URL        = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    CELERY_RESULT_BACKEND    = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # Upload umum
    UPLOAD_FOLDER  = os.getenv("UPLOAD_FOLDER",  "storage/uploads")
    MODELS_FOLDER  = os.getenv("MODELS_FOLDER",  "storage/models")
    MAX_CONTENT_LENGTH = 50 * 1024 * 1024          # 50 MB max upload (umum)

    # Konfigurasi khusus foto profil
    PROFILE_PHOTO_FOLDER = os.getenv("PROFILE_PHOTO_FOLDER", "storage/uploads/profile")
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
    MAX_PROFILE_PHOTO_SIZE = 2 * 1024 * 1024          # 2 MB


class DevelopmentConfig(BaseConfig):
    DEBUG = True
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        "mysql+mysqlconnector://root:@localhost/mindemy"
    )
    SQLALCHEMY_ECHO = False


class ProductionConfig(BaseConfig):
    DEBUG = False
    # Gunakan os.getenv dengan fallback None, atau biarkan error jika tidak diset
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL")
    if SQLALCHEMY_DATABASE_URI is None:
        raise ValueError("DATABASE_URL environment variable must be set in production!")
    SQLALCHEMY_POOL_RECYCLE  = 280
    SQLALCHEMY_POOL_TIMEOUT  = 20
    SQLALCHEMY_MAX_OVERFLOW  = 5


class TestingConfig(BaseConfig):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"


config_by_name = {
    "development": DevelopmentConfig,
    "production":  ProductionConfig,
    "testing":     TestingConfig,
}