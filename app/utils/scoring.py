"""
app/utils/scoring.py
────────────────────
Fungsi bantu untuk menghitung skor stres (total 40 item, skala 1-5)
dan skor motivasi SDI (28 item, skala 1-7), validasi jawaban,
serta klasifikasi berdasarkan threshold qcut.
"""

import numpy as np
<<<<<<< HEAD
from typing import Optional, Dict, Union
=======
from typing import Optional, Dict, Union, List
>>>>>>> 739bd89b5c85dd8759f5f30896c96b74b6781793


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
<<<<<<< HEAD
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
=======
# Saran Natural (Berdasarkan File PDF)
# ──────────────────────────────────────────────────────────────────

# Saran panjang untuk ditampilkan di detail
_DETAILED_SUGGESTIONS = {
    ("Tinggi", "Rendah"): [
        "Tarik napas perlahan selama 5 menit sampai badan terasa sedikit lebih tenang.",
        "Tulis tiga hal kecil yang tetap berjalan baik hari ini, sesederhana apa pun itu.",
        "Pecah satu tugas besar menjadi langkah 10-15 menit, lalu fokus pada langkah pertama saja.",
        "Kalau perlu, kabari teman dekat atau pasangan belajar agar ada yang ikut memantau progresmu.",
        "Ingat, tidak apa-apa berjalan lambat. Yang penting tetap bergerak.",
    ],
    ("Tinggi", "Sedang"): [
        "Batasi target harian ke tiga hal paling penting.",
        "Gunakan pola belajar 25 menit lalu istirahat 5 menit agar pikiran tidak cepat penuh.",
        "Usahakan tidur lebih teratur dan kurangi distraksi sebelum tidur.",
        "Sisihkan waktu 10 menit untuk jalan santai atau peregangan ringan.",
        "Jangan ragu untuk meminta bantuan jika merasa kewalahan.",
    ],
    ("Tinggi", "Tinggi"): [
        "Buat jeda pemulihan singkat di sela aktivitas, misalnya 10-15 menit setiap beberapa jam.",
        "Lakukan peregangan, jalan sebentar, atau lepas layar sejenak saat mulai terasa penat.",
        "Luangkan waktu untuk mengecek capaian mingguan agar kamu tetap merasa maju tanpa harus terus ngebut.",
        "Jangan tunggu benar-benar lelah untuk istirahat.",
        "Semangatmu bagus, tapi tetap jaga jeda agar tidak habis di tengah jalan.",
    ],
    ("Sedang", "Rendah"): [
        "Tanyakan ke diri sendiri, tugas ini akan berguna untuk tujuan apa dalam jangka panjang.",
        "Pasang target kecil yang realistis untuk satu minggu ke depan.",
        "Catat progres sederhana supaya kamu bisa melihat bahwa usahamu bergerak.",
        "Belajar bersama satu atau dua teman bisa membantu menjaga ritme.",
        "Coba ingat lagi tujuan belajarmu, lalu mulai dari target yang kecil tapi jelas.",
    ],
    ("Sedang", "Sedang"): [
        "Buat daftar tugas mingguan lalu urutkan dari yang paling penting.",
        "Gunakan teknik belajar yang membantu fokus, misalnya pomodoro.",
        "Cek kondisi diri secara singkat setiap malam, misalnya dengan bertanya apakah hari ini terlalu melelahkan atau masih terkendali.",
        "Jaga aktivitas fisik ringan beberapa kali dalam seminggu.",
        "Atur ritme belajar yang stabil supaya energi dan fokus tetap terjaga.",
    ],
    ("Sedang", "Tinggi"): [
        "Tetapkan jam belajar yang cukup konsisten.",
        "Luangkan beberapa menit untuk merefleksikan apa yang sudah selesai setiap hari.",
        "Ambil jeda aktif seperti jalan singkat, ngobrol dengan teman, atau minum air sebelum lanjut belajar.",
        "Pastikan ada ruang istirahat agar motivasi tidak cepat turun.",
        "Pertahankan pola yang sudah baik, lalu sisakan ruang untuk istirahat.",
    ],
    ("Rendah", "Rendah"): [
        "Mulai dengan sesi singkat 10 menit, tanpa target yang terlalu berat.",
        "Pilih satu tugas paling mudah agar kamu punya awal yang jelas.",
        "Tulis satu alasan pribadi kenapa kuliah atau tugas ini tetap penting buatmu.",
        "Cari teman, mentor, atau dosen yang bisa diajak bicara saat semangat terasa turun.",
        "Mulai dari hal paling ringan dulu. Yang penting bergerak, tidak harus langsung banyak.",
    ],
    ("Rendah", "Sedang"): [
        "Tentukan target harian yang jelas dan spesifik.",
        "Tinjau kembali progresmu di akhir hari.",
        "Pertahankan jam tidur yang cukup dan selingi aktivitas fisik ringan.",
        "Gunakan catatan atau kalender supaya perkembanganmu terlihat.",
        "Kamu sudah di jalur yang cukup baik. Tinggal jaga konsistensi setiap hari.",
    ],
    ("Rendah", "Tinggi"): [
        "Ambil tugas yang sedikit lebih menantang dari biasanya.",
        "Eksplor topik yang benar-benar kamu minati agar rasa ingin tahu tetap hidup.",
        "Kerja bareng teman pada proyek kecil bisa membantu memperluas sudut pandang.",
        "Jaga ritme yang sehat supaya kondisi ini bisa bertahan.",
        "Ini waktu yang pas untuk berkembang. Ambil tantangan baru secara bertahap.",
    ],
}

# Saran singkat untuk tampilan ringkas
_SHORT_SUGGESTIONS = {
    ("Tinggi", "Rendah"): "Ambil jeda sebentar, tenangkan pikiran, lalu kerjakan satu langkah kecil yang paling mungkin kamu selesaikan hari ini.",
    ("Tinggi", "Sedang"): "Turunkan beban dulu, rapikan prioritas, dan fokus ke hal yang benar-benar penting hari ini.",
    ("Tinggi", "Tinggi"): "Semangatmu bagus, tapi tetap jaga jeda agar tidak habis di tengah jalan.",
    ("Sedang", "Rendah"): "Coba ingat lagi tujuan belajarmu, lalu mulai dari target yang kecil tapi jelas.",
    ("Sedang", "Sedang"): "Atur ritme belajar yang stabil supaya energi dan fokus tetap terjaga.",
    ("Sedang", "Tinggi"): "Pertahankan pola yang sudah baik, lalu sisakan ruang untuk istirahat.",
    ("Rendah", "Rendah"): "Mulai dari hal paling ringan dulu. Yang penting bergerak, tidak harus langsung banyak.",
    ("Rendah", "Sedang"): "Kamu sudah di jalur yang cukup baik. Tinggal jaga konsistensi setiap hari.",
    ("Rendah", "Tinggi"): "Ini waktu yang pas untuk berkembang. Ambil tantangan baru secara bertahap.",
>>>>>>> 739bd89b5c85dd8759f5f30896c96b74b6781793
}


def generate_saran(tingkat_stres: str, tingkat_motivasi: str) -> str:
    """
<<<<<<< HEAD
    Menghasilkan saran berdasarkan kombinasi tingkat stres dan motivasi.
    """
    key = (tingkat_stres, tingkat_motivasi)
    return _SUGGESTIONS.get(
        key,
        "Silakan konsultasikan kondisi Anda dengan dosen wali."
=======
    Menghasilkan saran singkat berdasarkan kombinasi tingkat stres dan motivasi.
    """
    key = (tingkat_stres, tingkat_motivasi)
    return _SHORT_SUGGESTIONS.get(
        key,
        "Jaga kesehatan mentalmu dengan istirahat cukup dan aktivitas yang menyenangkan."
    )


def generate_detailed_suggestions(tingkat_stres: str, tingkat_motivasi: str) -> List[str]:
    """
    Menghasilkan daftar saran detail berdasarkan kombinasi tingkat stres dan motivasi.
    """
    key = (tingkat_stres, tingkat_motivasi)
    return _DETAILED_SUGGESTIONS.get(
        key,
        [
            "Atur jadwal belajar dengan istirahat cukup.",
            "Pastikan tidur 7-8 jam per malam.",
            "Lakukan aktivitas fisik ringan secara rutin.",
            "Jangan ragu untuk beristirahat jika merasa lelah.",
        ]
>>>>>>> 739bd89b5c85dd8759f5f30896c96b74b6781793
    )