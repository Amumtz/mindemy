"""
app/api/mahasiswa.py
────────────────────────────────────────────────────────
POST /api/mahasiswa/kuesioner           – submit jawaban (stress + motivasi)
GET  /api/mahasiswa/hasil/<nim>         – hasil skrining terbaru
GET  /api/mahasiswa/history             – riwayat semua skrining
GET  /api/mahasiswa/catatan             – catatan konseling dari dosen
"""

import json
import logging
import os
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, current_user
from app.extensions import db
from app.models import Mahasiswa, RiwayatSkrining
from app.utils.scoring import (
    compute_stress_score, compute_sdi_score,
    validate_stress_answers, validate_motivation_answers,
    generate_saran, score_to_category,
)
from app.ml.predictor import registry, audit_input,prepare_stress_input, prepare_motivasi_input
from app.models.mood_diary import MoodEntry, DiaryEntry
from datetime import datetime

logger = logging.getLogger(__name__)
mahasiswa_bp = Blueprint("mahasiswa", __name__)


# ── Decorator helper ─────────────────────────────────────────────
def mahasiswa_required(fn):
    """Ensures JWT role == 'mahasiswa' or 'admin'."""
    from functools import wraps
    @wraps(fn)
    @jwt_required()
    def wrapper(*args, **kwargs):
        if current_user.role not in ("mahasiswa", "admin"):
            return jsonify({"error": "Akses ditolak."}), 403
        return fn(*args, **kwargs)
    return wrapper


# ── Fungsi bantu untuk memastikan model siap (jika registry belum termuat) ─
def _ensure_model_loaded(model_type: str) -> bool:
    if registry.is_loaded(model_type):
        return True
    try:
        app = current_app._get_current_object()
        with app.app_context():
            from app.models import MLModel
            row = MLModel.query.filter_by(type=model_type, is_active=True).first()
            if not row or not os.path.exists(row.file_path):
                return False
            registry.load(model_type, row.file_path, row.to_dict() | {"thresholds": row.get_thresholds()})
            return True
    except Exception as e:
        logger.error(f"Gagal memuat model {model_type} on-demand: {e}")
        return False


# ── Submit kuesioner ─────────────────────────────────────────────
@mahasiswa_bp.route("/kuesioner", methods=["POST"])
@mahasiswa_required
def submit_kuesioner():
    data    = request.get_json(silent=True) or {}
    jawaban = data.get("jawaban", {})

    # Validasi
    err = validate_stress_answers(jawaban)
    if err:
        return jsonify({"error": f"Validasi stres: {err}"}), 422
    err = validate_motivation_answers(jawaban)
    if err:
        return jsonify({"error": f"Validasi motivasi: {err}"}), 422

    # Resolve NIM
    if current_user.role == "mahasiswa":
        nim = current_user.mahasiswa.NIM
    else:
        nim = data.get("NIM")
        if not nim:
            return jsonify({"error": "NIM wajib disertakan oleh admin."}), 400

    mhs = Mahasiswa.query.get(nim)
    if not mhs:
        return jsonify({"error": "Data mahasiswa tidak ditemukan."}), 404

    # Data demografi (gunakan nama field sesuai database)
    mhs_data = {
        "IPK": getattr(mhs, "IPK", 0.0),
        "Usia": getattr(mhs, "usia", 20),
        "Angkatan": getattr(mhs, "angkatan", ""),
        "Jurusan": mhs.jurusan.nama_jurusan if mhs.jurusan else "",
        "Gender": getattr(mhs, "gender", ""),
        "freq_olahraga": getattr(mhs, "freq_olahraga", ""),
        "durasi_tidur": getattr(mhs, "durasi_tidur", ""),
    }

    # Hitung skor mentah (untuk fallback)
    score_stress = compute_stress_score(jawaban)
    score_sdi    = compute_sdi_score(jawaban)

    # Pastikan model siap
    stress_loaded = _ensure_model_loaded("stress")
    motivasi_loaded = _ensure_model_loaded("motivasi")

    # Prediksi Stress
    if stress_loaded:
        try:
            input_stress = prepare_stress_input(mhs_data, jawaban)
            audit_input("stress", input_stress)   
            tingkat_stres = registry.predict("stress", input_stress)
        except Exception as e:
            logger.error(f"Gagal prediksi stress: {e}")
            tingkat_stres = _fallback_stress_category(score_stress)
    else:
        tingkat_stres = _fallback_stress_category(score_stress)

    # Prediksi Motivasi
    if motivasi_loaded:
        try:
            input_motivasi = prepare_motivasi_input(mhs_data, jawaban)
            tingkat_motivasi = registry.predict("motivasi", input_motivasi)
        except Exception as e:
            logger.error(f"Gagal prediksi motivasi: {e}")
            tingkat_motivasi = _fallback_motivasi_category(score_sdi)
    else:
        tingkat_motivasi = _fallback_motivasi_category(score_sdi)

    saran = generate_saran(tingkat_stres, tingkat_motivasi)

    # Simpan ke database
    skrining = RiwayatSkrining(
        NIM=nim,
        input_jawaban=json.dumps(jawaban),
        tingkat_stres=tingkat_stres,
        tingkat_motivasi=tingkat_motivasi,
        saran=saran,
        score_stress=score_stress,
        score_sdi=score_sdi,
    )
    db.session.add(skrining)
    db.session.commit()

    return jsonify({
        "message":         "Kuesioner berhasil disimpan.",
        "Id_skrining":     skrining.Id_skrining,
        "tingkat_stres":   tingkat_stres,
        "tingkat_motivasi":tingkat_motivasi,
        "score_stress":    score_stress,
        "score_sdi":       score_sdi,
        "saran":           saran,
    }), 201


# ── Hasil terbaru ─────────────────────────────────────────────────
@mahasiswa_bp.route("/hasil/<nim>", methods=["GET"])
@jwt_required()
def hasil(nim: str):
    if current_user.role == "mahasiswa" and current_user.mahasiswa.NIM != nim:
        return jsonify({"error": "Akses ditolak."}), 403

    row = (
        RiwayatSkrining.query
        .filter_by(NIM=nim)
        .order_by(RiwayatSkrining.tanggal_skrining.desc())
        .first()
    )
    if not row:
        return jsonify({"error": "Belum ada data skrining."}), 404

    return jsonify(row.to_dict())


# ── Riwayat semua ─────────────────────────────────────────────────
@mahasiswa_bp.route("/history", methods=["GET"])
@mahasiswa_required
def history():
    nim  = current_user.mahasiswa.NIM if current_user.role == "mahasiswa" else request.args.get("nim")
    page = request.args.get("page", 1, type=int)
    per  = request.args.get("per_page", 10, type=int)

    q = RiwayatSkrining.query.filter_by(NIM=nim).order_by(
        RiwayatSkrining.tanggal_skrining.desc()
    ).paginate(page=page, per_page=per, error_out=False)

    return jsonify({
        "data":        [r.to_dict() for r in q.items],
        "total":       q.total,
        "page":        q.page,
        "total_pages": q.pages,
    })


# ── Catatan konseling ─────────────────────────────────────────────
@mahasiswa_bp.route("/catatan", methods=["GET"])
@mahasiswa_required
def catatan():
    nim = current_user.mahasiswa.NIM if current_user.role == "mahasiswa" else request.args.get("nim")
    mhs = Mahasiswa.query.get_or_404(nim)
    return jsonify([c.to_dict() for c in mhs.catatan])


# ── Fallback ──────────────────────────────────────────────────────
def _fallback_stress_category(score: float) -> str:
    if score <= 60:   return "Rendah"
    if score <= 120:  return "Sedang"
    return "Tinggi"

def _fallback_motivasi_category(sdi: float) -> str:
    if sdi >= 3.0:   return "Tinggi"
    if sdi >= 0.0:   return "Sedang"
    return "Rendah"


# ── Profil ────────────────────────────────────────────────────────
@mahasiswa_bp.route("/profil", methods=["PUT"])
@jwt_required()
def update_profil():
    if current_user.role != "mahasiswa":
        return jsonify({"error": "Hanya mahasiswa yang dapat mengakses."}), 403

    mhs = current_user.mahasiswa
    data = request.get_json(silent=True) or {}

    if "angkatan" in data:
        mhs.angkatan = data["angkatan"]
    if "gender" in data:
        mhs.gender = data["gender"]
    if "usia" in data:
        try:
            mhs.usia = int(data["usia"])
        except (ValueError, TypeError):
            return jsonify({"error": "Usia harus berupa angka."}), 400
    if "freq_olahraga" in data:
        mhs.freq_olahraga = data["freq_olahraga"]
    if "durasi_tidur" in data:
        mhs.durasi_tidur = data["durasi_tidur"]
    if "IPK" in data:
        try:
            ipk = float(data["IPK"])
            if not (0.0 <= ipk <= 4.0):
                return jsonify({"error": "IPK harus antara 0.00 dan 4.00"}), 400
            mhs.IPK = ipk
        except (ValueError, TypeError):
            return jsonify({"error": "IPK harus berupa angka."}), 400

    db.session.commit()
    return jsonify({
        "message": "Profil berhasil diperbarui.",
        "data": mhs.to_dict()
    })


@mahasiswa_bp.route("/profil/status", methods=["GET"])
@jwt_required()
def profil_status():
    if current_user.role != "mahasiswa":
        return jsonify({"error": "Hanya mahasiswa yang dapat mengakses."}), 403

    mhs = current_user.mahasiswa
    required = ["angkatan", "gender", "usia", "freq_olahraga", "durasi_tidur"]
    missing = [f for f in required if not getattr(mhs, f)]
    return jsonify({
        "is_complete": len(missing) == 0,
        "missing_fields": missing
    })

# ── Mood & Diary Routes ─────────────────────────────────────────────

@mahasiswa_bp.route("/mood", methods=["POST"])
@mahasiswa_required
def add_mood():
    """Tambah catatan mood harian (1-5)"""
    data = request.get_json(silent=True) or {}
    nim = data.get("nim")
    date_str = data.get("date")      # format YYYY-MM-DD
    mood_value = data.get("mood_value")

    if current_user.role == "mahasiswa":
        nim = current_user.mahasiswa.NIM
    else:
        if not nim:
            return jsonify({"error": "NIM wajib disertakan oleh admin."}), 400

    if not date_str or mood_value is None:
        return jsonify({"error": "date dan mood_value wajib diisi."}), 400

    try:
        mood_value = int(mood_value)
        if not (1 <= mood_value <= 5):
            return jsonify({"error": "mood_value harus antara 1-5."}), 400
    except ValueError:
        return jsonify({"error": "mood_value harus berupa angka."}), 400

    try:
        date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"error": "format date harus YYYY-MM-DD."}), 400

    mhs = Mahasiswa.query.get(nim)
    if not mhs:
        return jsonify({"error": "Mahasiswa tidak ditemukan."}), 404

    new_mood = MoodEntry(nim=nim, date=date_obj, mood_value=mood_value)
    db.session.add(new_mood)
    db.session.commit()
    return jsonify(new_mood.to_dict()), 201


@mahasiswa_bp.route("/diary", methods=["POST"])
@mahasiswa_required
def add_diary():
    """Tambah entri diary (bisa banyak per hari)"""
    data = request.get_json(silent=True) or {}
    nim = data.get("nim")
    date_str = data.get("date")
    title = data.get("title", "")
    content = data.get("content")

    if current_user.role == "mahasiswa":
        nim = current_user.mahasiswa.NIM
    else:
        if not nim:
            return jsonify({"error": "NIM wajib disertakan oleh admin."}), 400

    if not date_str or not content:
        return jsonify({"error": "date dan content wajib diisi."}), 400

    try:
        date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"error": "format date harus YYYY-MM-DD."}), 400

    mhs = Mahasiswa.query.get(nim)
    if not mhs:
        return jsonify({"error": "Mahasiswa tidak ditemukan."}), 404

    new_diary = DiaryEntry(nim=nim, date=date_obj, title=title, content=content)
    db.session.add(new_diary)
    db.session.commit()
    return jsonify(new_diary.to_dict()), 201


@mahasiswa_bp.route("/mood/<nim>", methods=["GET"])
@jwt_required()
def get_mood_by_nim(nim):
    """Ambil semua mood mahasiswa berdasarkan NIM (terbaru di atas)"""
    if current_user.role == "mahasiswa" and current_user.mahasiswa.NIM != nim:
        return jsonify({"error": "Akses ditolak."}), 403

    moods = MoodEntry.query.filter_by(nim=nim).order_by(
        MoodEntry.date.desc(), MoodEntry.created_at.desc()
    ).all()
    return jsonify([m.to_dict() for m in moods])


@mahasiswa_bp.route("/diary/<nim>", methods=["GET"])
@jwt_required()
def get_diary_by_nim(nim):
    """Ambil semua diary mahasiswa"""
    if current_user.role == "mahasiswa" and current_user.mahasiswa.NIM != nim:
        return jsonify({"error": "Akses ditolak."}), 403

    diaries = DiaryEntry.query.filter_by(nim=nim).order_by(
        DiaryEntry.date.desc(), DiaryEntry.created_at.desc()
    ).all()
    return jsonify([d.to_dict() for d in diaries])


@mahasiswa_bp.route("/mood/<int:id>", methods=["PUT"])
@mahasiswa_required
def update_mood(id):
    """Update mood_value (dan opsional date) berdasarkan id entry"""
    mood = MoodEntry.query.get_or_404(id)
    if current_user.role == "mahasiswa" and current_user.mahasiswa.NIM != mood.nim:
        return jsonify({"error": "Akses ditolak."}), 403

    data = request.get_json(silent=True) or {}
    if "mood_value" in data:
        try:
            val = int(data["mood_value"])
            if 1 <= val <= 5:
                mood.mood_value = val
            else:
                return jsonify({"error": "mood_value harus 1-5."}), 400
        except ValueError:
            return jsonify({"error": "mood_value harus angka."}), 400
    if "date" in data:
        try:
            mood.date = datetime.strptime(data["date"], "%Y-%m-%d").date()
        except ValueError:
            return jsonify({"error": "format date YYYY-MM-DD."}), 400

    db.session.commit()
    return jsonify(mood.to_dict())


@mahasiswa_bp.route("/diary/<int:id>", methods=["PUT"])
@mahasiswa_required
def update_diary(id):
    """Update title, content, atau date diary"""
    diary = DiaryEntry.query.get_or_404(id)
    if current_user.role == "mahasiswa" and current_user.mahasiswa.NIM != diary.nim:
        return jsonify({"error": "Akses ditolak."}), 403

    data = request.get_json(silent=True) or {}
    if "title" in data:
        diary.title = data["title"]
    if "content" in data:
        diary.content = data["content"]
    if "date" in data:
        try:
            diary.date = datetime.strptime(data["date"], "%Y-%m-%d").date()
        except ValueError:
            return jsonify({"error": "format date YYYY-MM-DD."}), 400

    db.session.commit()
    return jsonify(diary.to_dict())


@mahasiswa_bp.route("/mood/<int:id>", methods=["DELETE"])
@mahasiswa_required
def delete_mood(id):
    """Hapus mood entry berdasarkan id"""
    mood = MoodEntry.query.get_or_404(id)
    if current_user.role == "mahasiswa" and current_user.mahasiswa.NIM != mood.nim:
        return jsonify({"error": "Akses ditolak."}), 403

    db.session.delete(mood)
    db.session.commit()
    return jsonify({"message": "Mood entry dihapus."}), 200


@mahasiswa_bp.route("/diary/<int:id>", methods=["DELETE"])
@mahasiswa_required
def delete_diary(id):
    """Hapus diary entry berdasarkan id"""
    diary = DiaryEntry.query.get_or_404(id)
    if current_user.role == "mahasiswa" and current_user.mahasiswa.NIM != diary.nim:
        return jsonify({"error": "Akses ditolak."}), 403

    db.session.delete(diary)
    db.session.commit()
    return jsonify({"message": "Diary entry dihapus."}), 200