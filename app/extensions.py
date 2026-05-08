# app/extensions.py
from flask_sqlalchemy import SQLAlchemy
from flask_jwt_extended import JWTManager
from flask_cors import CORS
from celery import Celery
from flask_migrate import Migrate      

db = SQLAlchemy()
jwt = JWTManager()
cors = CORS()
celery = Celery()
migrate = Migrate()                   