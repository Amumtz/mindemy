"""
app/utils/scoring.py
────────────────────
Fungsi bantu untuk menghitung skor stres (total 40 item, skala 1-5)
dan skor motivasi SDI (28 item, skala 1-7), validasi jawaban,
serta klasifikasi berdasarkan threshold qcut.
"""

import numpy as np
from typing import Optional, Dict, Union


# ──────────────────────────────────────────────────────────────────
# Konstanta Kolom
# ──────────────────────────────────────────────────────────────────

STRESS_COLS = [f"S{i}" for i in range(1, 41)]          # S1 – S40
MOTIVATION_COLS = [f"M{i}" for i in range(1, 29)]      # M1 – M28

# Sub-skala untuk SDI (masing-masing 4 item)
SUBSKALA_MOTIVASI = {
    "im_know":     ["M1", "M2", "M3", "M4"],
    "im_acc":      ["M5", "M6", "M7", "M8"],
    "im_stim":     ["M9", "M10", "M11", "M12"],
    "identified":  ["M13", "M14", "M15", "M16"],
    "introjected": ["M17", "M18", "M19", "M20"],
    "external":    ["M21", "M22", "M23", "M24"],
    "amotivation": ["M25", "M26", "M27", "M28"],
}


# ──────────────────────────────────────────────────────────────────
# Perhitungan Skor
# ──────────────────────────────────────────────────────────────────

def compute_stress_score(answers: Dict[str, Union[int, float]]) -> float:
    """
    Menghitung total skor stres dari 40 item (skala 1-5).
    """
    total = 0.0
    for col in STRESS_COLS:
        val = answers.get(col)
        if val is not None:
            total += float(val)
    return total


def compute_sdi_score(answers: Dict[str, Union[int, float]]) -> float:
    """
    Menghitung Self-Determination Index (SDI) berdasarkan 28 item motivasi.
    Skala item 1-7.

    Formula:
        SDI = 2 * (rata-rata IM total) + 1 * (rata-rata Identified)
              - 1 * (rata-rata Controlled Extrinsic) - 2 * (rata-rata Amotivation)

    di mana:
        IM total = (im_know + im_acc + im_stim) / 3
        Controlled Extrinsic = (introjected + external) / 2
    """
    # Hitung rata-rata tiap subskala
    means = {}
    for key, cols in SUBSKALA_MOTIVASI.items():
        vals = [float(answers.get(c, 0)) for c in cols]
        means[key] = np.mean(vals) if vals else 0.0

    intrinsic_total = (means["im_know"] + means["im_acc"] + means["im_stim"]) / 3.0
    controlled_extrinsic = (means["introjected"] + means["external"]) / 2.0

    sdi = (2.0 * intrinsic_total) + (1.0 * means["identified"]) \
          - (1.0 * controlled_extrinsic) - (2.0 * means["amotivation"])

    return round(float(sdi), 4)


# ──────────────────────────────────────────────────────────────────
# Klasifikasi Berdasarkan Threshold qcut
# ──────────────────────────────────────────────────────────────────

def score_to_category(score: float, thresholds: Dict[str, float]) -> str:
    """
    thresholds format (dari qcut saat training):
        {"low_upper": batas_atas_rendah, "high_lower": batas_bawah_tinggi}

    Aturan:
        score <= low_upper          → Rendah
        score >= high_lower         → Tinggi
        selainnya                   → Sedang
    """
    low_upper = thresholds.get("low_upper", float("inf"))
    high_lower = thresholds.get("high_lower", float("-inf"))

    if score <= low_upper:
        return "Rendah"
    elif score >= high_lower:
        return "Tinggi"
    else:
        return "Sedang"


# ──────────────────────────────────────────────────────────────────
# Validasi Jawaban
# ──────────────────────────────────────────────────────────────────

def validate_stress_answers(answers: Dict) -> Optional[str]:
    """
    Memeriksa apakah semua item S1-S40 ada dan bernilai integer 1-5.
    """
    for i in range(1, 41):
        key = f"S{i}"
        val = answers.get(key)
        if val is None:
            return f"Jawaban {key} tidak ditemukan."
        try:
            ival = int(val)
        except (ValueError, TypeError):
            return f"Nilai {key} harus berupa angka, ditemukan: {val}"
        if not (1 <= ival <= 5):
            return f"Nilai {key} harus antara 1-5, ditemukan: {ival}"
    return None


def validate_motivation_answers(answers: Dict) -> Optional[str]:
    """
    Memeriksa apakah semua item M1-M28 ada dan bernilai integer 1-7.
    """
    for i in range(1, 29):
        key = f"M{i}"
        val = answers.get(key)
        if val is None:
            return f"Jawaban {key} tidak ditemukan."
        try:
            ival = int(val)
        except (ValueError, TypeError):
            return f"Nilai {key} harus berupa angka, ditemukan: {val}"
        if not (1 <= ival <= 7):
            return f"Nilai {key} harus antara 1-7, ditemukan: {ival}"
    return None


# ──────────────────────────────────────────────────────────────────
# Saran Otomatis
# ──────────────────────────────────────────────────────────────────

_SUGGESTIONS = {
    ("Rendah", "Tinggi"): (
        "Stres Anda terkendali dan motivasi Anda sangat baik! Pertahankan gaya hidup sehat "
        "dan terus kembangkan potensi diri."
    ),
    ("Sedang", "Tinggi"): (
        "Motivasi Anda tinggi, namun mulai ada tekanan stres. Pastikan waktu istirahat "
        "cukup dan manfaatkan motivasi positif untuk mengatasi tantangan."
    ),
    ("Tinggi", "Tinggi"): (
        "Stres Anda cukup tinggi meski motivasi masih baik. Segera konsultasikan dengan "
        "dosen wali atau konselor untuk mendapatkan dukungan."
    ),
    ("Rendah", "Sedang"): (
        "Kondisi cukup baik. Coba eksplorasi kegiatan atau metode belajar baru untuk "
        "meningkatkan motivasi Anda lebih lanjut."
    ),
    ("Sedang", "Sedang"): (
        "Perhatikan keseimbangan belajar dan istirahat. Cari lingkungan belajar yang "
        "lebih suportif untuk meningkatkan motivasi."
    ),
    ("Tinggi", "Sedang"): (
        "Tingkat stres Anda mengkhawatirkan. Segera bicarakan dengan dosen wali dan "
        "terapkan teknik manajemen stres (olahraga, meditasi, dll.)."
    ),
    ("Rendah", "Rendah"): (
        "Motivasi Anda perlu ditingkatkan. Coba tetapkan tujuan jangka pendek yang "
        "terukur dan cari dukungan dari teman atau mentor."
    ),
    ("Sedang", "Rendah"): (
        "Kombinasi stres sedang dan motivasi rendah perlu perhatian. Diskusikan kondisi "
        "ini dengan dosen wali Anda sesegera mungkin."
    ),
    ("Tinggi", "Rendah"): (
        "Kondisi ini memerlukan perhatian segera. Sangat disarankan untuk berkonsultasi "
        "dengan konselor atau psikolog kampus dalam waktu dekat."
    ),
}


def generate_saran(tingkat_stres: str, tingkat_motivasi: str) -> str:
    """
    Menghasilkan saran berdasarkan kombinasi tingkat stres dan motivasi.
    """
    key = (tingkat_stres, tingkat_motivasi)
    return _SUGGESTIONS.get(
        key,
        "Silakan konsultasikan kondisi Anda dengan dosen wali."
    )