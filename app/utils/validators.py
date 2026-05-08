"""
app/utils/validators.py
───────────────────────
Kumpulan fungsi validasi untuk request payload.
"""

import re
from typing import Optional, Any


# ──────────────────────────────────────────────────────────────────
# Validasi Umum
# ──────────────────────────────────────────────────────────────────

def validate_required_fields(data: dict, required_fields: list) -> Optional[str]:
    """
    Memeriksa apakah semua field wajib ada dan tidak kosong.
    Returns pesan error atau None jika valid.
    """
    for field in required_fields:
        if field not in data or data[field] is None:
            return f"Field '{field}' wajib diisi."
        if isinstance(data[field], str) and not data[field].strip():
            return f"Field '{field}' tidak boleh kosong."
    return None


def validate_email(email: str) -> bool:
    """Memvalidasi format email sederhana."""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None


def validate_nim_format(nim: str) -> bool:
    """
    Validasi format NIM.
    Contoh: NIM berupa 8-12 karakter alfanumerik (sesuaikan dengan aturan institusi).
    NIM pada data Anda: '607012300200' (12 digit angka).
    """
    return bool(re.match(r'^\d{12}$', nim))


def validate_nip_format(nip: str) -> bool:
    """Contoh validasi NIP dosen (8 digit angka)."""
    return bool(re.match(r'^\d{8}$', nip))


def validate_angkatan(angkatan: str) -> bool:
    """Angkatan berupa 4 digit tahun, misal '2023'."""
    return bool(re.match(r'^\d{4}$', angkatan))


# ──────────────────────────────────────────────────────────────────
# Validasi Rentang Nilai
# ──────────────────────────────────────────────────────────────────

def validate_range(value: Any, min_val: float, max_val: float, field_name: str = "Nilai") -> Optional[str]:
    """
    Memeriksa apakah nilai numerik berada dalam rentang tertentu.
    Returns pesan error atau None.
    """
    try:
        num = float(value)
    except (ValueError, TypeError):
        return f"{field_name} harus berupa angka."

    if not (min_val <= num <= max_val):
        return f"{field_name} harus antara {min_val} dan {max_val}."
    return None


def validate_ipk(ipk: Any) -> Optional[str]:
    """Validasi IPK antara 0.00 - 4.00."""
    return validate_range(ipk, 0.0, 4.0, "IPK")


def validate_usia(usia: Any) -> Optional[str]:
    """Validasi usia mahasiswa (misal 16 - 100)."""
    return validate_range(usia, 16, 100, "Usia")


# ──────────────────────────────────────────────────────────────────
# Validasi Pilihan Enum
# ──────────────────────────────────────────────────────────────────

def validate_olahraga(value: str) -> bool:
    """Memeriksa apakah value termasuk pilihan yang valid."""
    valid_options = ["Tidak pernah", "1-2 kali", "3-4 kali", ">4 kali"]
    return value in valid_options


def validate_tidur(value: str) -> bool:
    """Memeriksa pilihan durasi tidur."""
    valid_options = ["< 4 Jam", "4-5 Jam", "6-7 Jam", "> 7 Jam"]
    return value in valid_options