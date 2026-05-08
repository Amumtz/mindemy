# app/models/__init__.py
from .user import User
from .jurusan import Jurusan
from .dosen import Dosen
from .mahasiswa import Mahasiswa
from .catatan_konseling import CatatanKonseling
from .riwayat_skrining import RiwayatSkrining
from .ml_model import MLModel, TrainingHistory, Dataset

__all__ = [
    "User",
    "Jurusan",
    "Dosen",
    "Mahasiswa",
    "CatatanKonseling",
    "RiwayatSkrining",
    "MLModel",
    "TrainingHistory",
    "Dataset",
]