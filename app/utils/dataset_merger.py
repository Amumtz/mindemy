# app/utils/dataset_merger.py
import os
import pandas as pd
from datetime import datetime
from flask import current_app
from app.extensions import db
from app.models import RiwayatSkrining, Mahasiswa, Jurusan

def load_initial_dataset(file_path: str) -> pd.DataFrame:
    """Muat dataset awal dari file Excel/CSV yang digunakan saat pertama kali training."""
    if file_path.endswith('.xlsx'):
        return pd.read_excel(file_path)
    else:
        return pd.read_csv(file_path)

def fetch_new_data_from_db(limit: int = None, start_date: str = None, end_date: str = None) -> pd.DataFrame:
    """
    Ambil data kuesioner dari database, konversi ke format yang sama dengan dataset awal.
    Kolom yang dihasilkan: 
        Jurusan, Angkatan, Gender, Usia, IPK, freq_olahraga, durasi_tidur,
        S1..S40, M1..M28, serta tingkat_stres dan tingkat_motivasi (bisa digunakan sebagai label).
    """
    query = db.session.query(
        RiwayatSkrining,
        Mahasiswa,
        Jurusan
    ).join(
        Mahasiswa, RiwayatSkrining.NIM == Mahasiswa.NIM
    ).join(
        Jurusan, Mahasiswa.id_jurusan == Jurusan.Id_Jurusan, isouter=True
    ).order_by(RiwayatSkrining.tanggal_skrining.desc())

    if start_date:
        query = query.filter(RiwayatSkrining.tanggal_skrining >= start_date)
    if end_date:
        query = query.filter(RiwayatSkrining.tanggal_skrining <= end_date)
    if limit:
        query = query.limit(limit)

    results = query.all()

    rows = []
    for skrining, mhs, jur in results:
        jawaban = skrining.get_jawaban()  # asumsi model Anda punya method ini
        row = {
            "Jurusan": jur.nama_jurusan if jur else "",
            "Angkatan": mhs.angkatan or "",
            "Gender": mhs.gender or "",
            "Usia": mhs.usia or "",
            "IPK": mhs.IPK or "",
            "freq_olahraga": mhs.freq_olahraga or "",
            "durasi_tidur": mhs.durasi_tidur or "",
            # Skor stres/motivasi hasil prediksi (sudah ada di RiwayatSkrining)
            "tingkat_stres": skrining.tingkat_stres,
            "tingkat_motivasi": skrining.tingkat_motivasi,
            # Atau jika ingin menggunakan score mentah (misal skor SDI/stress)
            "score_stress": skrining.score_stress,   # asumsi ada kolom score_stress
            "score_motivasi": skrining.score_motivasi,
        }
        # Tambahkan S1..S40
        for i in range(1, 41):
            row[f"S{i}"] = jawaban.get(f"S{i}", 0)
        # Tambahkan M1..M28
        for i in range(1, 29):
            row[f"M{i}"] = jawaban.get(f"M{i}", 0)
        rows.append(row)

    return pd.DataFrame(rows)

def merge_datasets(initial_df: pd.DataFrame, new_df: pd.DataFrame) -> pd.DataFrame:
    """
    Gabungkan dataset awal dan data baru.
    Pastikan kolom-kolom sama (urutan dan nama).
    """
    # Pastikan kolom sama
    common_cols = list(set(initial_df.columns) & set(new_df.columns))
    # Urutkan kolom seperti pada initial_df
    final_cols = [col for col in initial_df.columns if col in common_cols]
    merged = pd.concat([initial_df[final_cols], new_df[final_cols]], ignore_index=True)
    return merged

def get_dataset_comparison_stats(initial_path: str, limit_new: int = None) -> dict:
    """Hitung statistik perbandingan antara dataset awal dan data baru (n baris terbaru)."""
    initial_df = load_initial_dataset(initial_path)
    new_df = fetch_new_data_from_db(limit=limit_new)  # ambil semua atau batasi

    # Hitung statistik dasar
    old_count = len(initial_df)
    new_count = len(new_df)

    # Rata-rata skor (jika ada kolom score_stress / score_motivasi)
    old_avg_stress = initial_df.get('score_stress', initial_df.get('S_total', pd.Series([0]))).mean()
    old_avg_motivasi = initial_df.get('score_motivasi', initial_df.get('M_total', pd.Series([0]))).mean()
    new_avg_stress = new_df.get('score_stress', pd.Series([0])).mean() if new_count > 0 else 0
    new_avg_motivasi = new_df.get('score_motivasi', pd.Series([0])).mean() if new_count > 0 else 0

    # Distribusi tingkat stres (Rendah/Sedang/Tinggi) dari database
    stress_dist = {"Rendah": 0, "Sedang": 0, "Tinggi": 0}
    motiv_dist = {"Rendah": 0, "Sedang": 0, "Tinggi": 0}
    if new_count > 0 and 'tingkat_stres' in new_df.columns:
        for val in new_df['tingkat_stres']:
            if val in stress_dist:
                stress_dist[val] += 1
    if new_count > 0 and 'tingkat_motivasi' in new_df.columns:
        for val in new_df['tingkat_motivasi']:
            if val in motiv_dist:
                motiv_dist[val] += 1

    return {
        "initial_count": old_count,
        "new_count": new_count,
        "initial_avg_stress": float(old_avg_stress),
        "initial_avg_motivation": float(old_avg_motivasi),
        "new_avg_stress": float(new_avg_stress),
        "new_avg_motivation": float(new_avg_motivasi),
        "new_stress_distribution": stress_dist,
        "new_motivation_distribution": motiv_dist,
        "last_new_data_date": new_df['tanggal_skrining'].max() if new_count > 0 and 'tanggal_skrining' in new_df.columns else None
    }