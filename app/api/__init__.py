# app/api/__init__.py
"""
Blueprint API endpoints.
"""

from .auth import auth_bp
from .admin import admin_bp
from .mahasiswa import mahasiswa_bp
from .dosen import dosen_bp

__all__ = [
    "auth_bp",
    "admin_bp",
    "mahasiswa_bp",
    "dosen_bp",
]