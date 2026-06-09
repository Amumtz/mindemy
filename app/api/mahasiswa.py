"""
app/api/mahasiswa.py
────────────────────────────────────────────────────────
POST /api/mahasiswa/kuesioner           – submit jawaban (stress + motivasi)
GET  /api/mahasiswa/hasil/<nim>         – hasil skrining terbaru
GET  /api/mahasiswa/history             – riwayat semua skrining
GET  /api/mahasiswa/catatan             – catatan konseling dari dosen
GET  /api/mahasiswa/can_submit/<nim>    – cek apakah bisa submit kuesioner (1x seminggu)
PUT  /api/mahasiswa/profil/foto         – upload foto profil
GET  /api/mahasiswa/profil/foto/<nim>   – ambil foto profil
DELETE /api/mahasiswa/profil/foto/<nim> – hapus foto profil
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
    generate_saran, generate_detailed_suggestions,
    score_to_category,
)
from app.ml.predictor import registry, prepare_stress_input, prepare_motivasi_input
from app.models.mood_diary import MoodEntry, DiaryEntry
from datetime import datetime, timedelta
from app.utils.file_upload import save_profile_picture
from werkzeug.exceptions import BadRequest
import time

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


# ── CEK APAKAH BISA SUBMIT KUESIONER (1x SEMINGGU) ─────────────────────
@mahasiswa_bp.route("/can_submit/<nim>", methods=["GET"])
@jwt_required()
def can_submit_kuesioner(nim: str):
    """Cek apakah mahasiswa bisa submit kuesioner (1x dalam 7 hari)"""
    # Validasi akses
    if current_user.role == "mahasiswa" and current_user.mahasiswa.NIM != nim:
        return jsonify({"error": "Akses ditolak."}), 403
    
    mhs = Mahasiswa.query.get(nim)
    if not mhs:
        return jsonify({"error": "Mahasiswa tidak ditemukan."}), 404
    
    # Cari skrining terakhir dalam 7 hari terakhir
    one_week_ago = datetime.utcnow() - timedelta(days=7)
    
    last_skrining = (
        RiwayatSkrining.query
        .filter_by(NIM=nim)
        .filter(RiwayatSkrining.tanggal_skrining >= one_week_ago)
        .order_by(RiwayatSkrining.tanggal_skrining.desc())
        .first()
    )
    
    if last_skrining:
        # Hitung hari yang tersisa
        days_passed = (datetime.utcnow() - last_skrining.tanggal_skrining).days
        days_remaining = max(0, 7 - days_passed)
        
        return jsonify({
            "can_submit": False,
            "message": f"Anda sudah mengisi kuesioner pada {last_skrining.tanggal_skrining.strftime('%d %B %Y')}. "
                      f"Silakan kembali dalam {days_remaining} hari untuk mengisi kembali.",
            "last_submission_date": last_skrining.tanggal_skrining.isoformat(),
            "days_remaining": days_remaining
        }), 200
    else:
        return jsonify({
            "can_submit": True,
            "message": "Anda dapat mengisi kuesioner.",
            "last_submission_date": None,
            "days_remaining": 0
        }), 200


# ── Submit kuesioner ─────────────────────────────────────────────
@mahasiswa_bp.route("/kuesioner", methods=["POST"])
@mahasiswa_required
def submit_kuesioner():
    data    = request.get_json(silent=True) or {}
    jawaban = data.get("jawaban", {})

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

    # 🔥 CEK BATASAN 1x SEMINGGU (HANYA UNTUK MAHASISWA, ADMIN BISA LEWAT)
    if current_user.role == "mahasiswa":
        one_week_ago = datetime.utcnow() - timedelta(days=7)
        last_skrining = (
            RiwayatSkrining.query
            .filter_by(NIM=nim)
            .filter(RiwayatSkrining.tanggal_skrining >= one_week_ago)
            .first()
        )
        
        if last_skrining:
            days_passed = (datetime.utcnow() - last_skrining.tanggal_skrining).days
            days_remaining = 7 - days_passed
            return jsonify({
                "error": "Batasan Mingguan",
                "message": f"Anda sudah mengisi kuesioner minggu ini. Silakan kembali dalam {days_remaining} hari.",
                "last_submission_date": last_skrining.tanggal_skrining.isoformat(),
                "days_remaining": days_remaining
            }), 403

    # 🔥 UPDATE DATA FREKUENSI OLAHRAGA DAN DURASI TIDUR DARI USER
    if "freq_olahraga" in jawaban:
        mhs.freq_olahraga = jawaban["freq_olahraga"]
    if "durasi_tidur" in jawaban:
        mhs.durasi_tidur = jawaban["durasi_tidur"]
    
    db.session.commit()

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

    # Pisahkan jawaban stres (S1-S40) dan motivasi (M1-M28)
    stress_answers = {}
    motivation_answers = {}
    
    for key, value in jawaban.items():
        if key.startswith('S'):
            stress_answers[key] = value
        elif key.startswith('M'):
            motivation_answers[key] = value

    # Hitung skor mentah (untuk fallback)
    score_stress = compute_stress_score(stress_answers)
    score_sdi    = compute_sdi_score(motivation_answers)

    # Pastikan model siap
    stress_loaded = _ensure_model_loaded("stress")
    motivasi_loaded = _ensure_model_loaded("motivasi")

    # Prediksi Stress
    if stress_loaded:
        try:
            input_stress = prepare_stress_input(mhs_data, stress_answers)
            tingkat_stres = registry.predict("stress", input_stress)
        except Exception as e:
            logger.error(f"Gagal prediksi stress: {e}")
            tingkat_stres = _fallback_stress_category(score_stress)
    else:
        tingkat_stres = _fallback_stress_category(score_stress)

    # Prediksi Motivasi
    if motivasi_loaded:
        try:
            input_motivasi = prepare_motivasi_input(mhs_data, motivation_answers)
            tingkat_motivasi = registry.predict("motivasi", input_motivasi)
        except Exception as e:
            logger.error(f"Gagal prediksi motivasi: {e}")
            tingkat_motivasi = _fallback_motivasi_category(score_sdi)
    else:
        tingkat_motivasi = _fallback_motivasi_category(score_sdi)

    # 🔥 GENERATE SARAN (singkat dan detail)
    saran = generate_saran(tingkat_stres, tingkat_motivasi)
    detailed_suggestions = generate_detailed_suggestions(tingkat_stres, tingkat_motivasi)

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

    # 🔥 KIRIM JUGA detailed_suggestions
    return jsonify({
        "message":              "Kuesioner berhasil disimpan.",
        "Id_skrining":          skrining.Id_skrining,
        "tingkat_stres":        tingkat_stres,
        "tingkat_motivasi":     tingkat_motivasi,
        "score_stress":         score_stress,
        "score_sdi":            score_sdi,
        "saran":                saran,
        "detailed_suggestions": detailed_suggestions,
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


# ============ TAMBAHKAN INI ============
@mahasiswa_bp.route("/suggestions/detail", methods=["GET"])
@jwt_required()
def get_detailed_suggestions_endpoint():
    """Ambil saran detail berdasarkan tingkat stres dan motivasi"""
    stress = request.args.get("stress", "")
    motivation = request.args.get("motivation", "")
    
    if not stress or not motivation:
        return jsonify({"error": "Parameter stress dan motivation wajib diisi."}), 400
    
    from app.utils.scoring import generate_detailed_suggestions
    suggestions = generate_detailed_suggestions(stress, motivation)
    
    return jsonify({"suggestions": suggestions}), 200


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
    """Tambah atau update catatan mood harian (1-5) - hanya satu per hari"""
    data = request.get_json(silent=True) or {}
    nim = data.get("nim")
    date_str = data.get("date")
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

    existing_mood = MoodEntry.query.filter_by(nim=nim, date=date_obj).first()
    
    if existing_mood:
        existing_mood.mood_value = mood_value
        existing_mood.updated_at = datetime.now()
        db.session.commit()
        return jsonify(existing_mood.to_dict()), 200
    else:
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


# ============ FOTO PROFIL ENDPOINTS ============

@mahasiswa_bp.route("/profil/foto", methods=["PUT"])
@jwt_required()
def upload_foto_profil():
    if current_user.role != "mahasiswa":
        return jsonify({"error": "Hanya mahasiswa yang dapat mengakses."}), 403

    mhs = current_user.mahasiswa
    
    if 'foto' not in request.files:
        return jsonify({"error": "Tidak ada file foto yang dikirim."}), 400
    
    file = request.files['foto']
    if file.filename == '':
        return jsonify({"error": "Nama file kosong."}), 400
    
    try:
        # Simpan file dan dapatkan path relatif
        relative_path = save_profile_picture(file, mhs.NIM)
        
        # Hapus foto lama jika ada
        if mhs.foto_profil:
            root_dir = os.path.dirname(current_app.root_path)
            old_path = os.path.join(root_dir, mhs.foto_profil)
            if os.path.exists(old_path):
                os.remove(old_path)
                print(f"🗑️ Foto lama dihapus: {old_path}")
        
        mhs.foto_profil = relative_path
        db.session.commit()
        
        return jsonify({
            "message": "Foto profil berhasil diunggah.",
            "foto_profil": relative_path
        }), 200
        
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Gagal upload foto: {e}")
        return jsonify({"error": "Terjadi kesalahan saat menyimpan foto."}), 500


# 🔥 PERBAIKAN: Endpoint GET foto - TANPA AUTHENTIKASI
@mahasiswa_bp.route("/profil/foto/<nim>", methods=["GET"])
# @jwt_required()  # <-- HAPUS/TAMBAHKAN COMMENT INI
def get_foto_profil(nim):
    # HAPUS pengecekan role
    # if current_user.role == "mahasiswa" and current_user.mahasiswa.NIM != nim:
    #     return jsonify({"error": "Akses ditolak."}), 403
    
    mhs = Mahasiswa.query.get(nim)
    if not mhs or not mhs.foto_profil:
        return jsonify({"error": "Foto profil tidak ditemukan."}), 404
    
    # Cari file di beberapa kemungkinan lokasi
    root_dir = os.path.dirname(current_app.root_path)
    filename = os.path.basename(mhs.foto_profil)
    
    possible_paths = [
        os.path.join(root_dir, mhs.foto_profil),
        os.path.join(root_dir, 'storage', 'uploads', filename),
        os.path.join(current_app.root_path, 'storage', 'uploads', filename),
    ]
    
    file_path = None
    for path in possible_paths:
        if os.path.exists(path):
            file_path = path
            print(f"✅ Foto ditemukan di: {path}")
            break
    
    if not file_path:
        print(f"❌ Foto tidak ditemukan. DB path: {mhs.foto_profil}")
        return jsonify({"error": "File foto tidak ada di server."}), 404
    
    from flask import send_file
    return send_file(file_path, mimetype='image/jpeg')


# ============ DELETE FOTO PROFIL ============

@mahasiswa_bp.route("/profil/foto/<nim>", methods=["DELETE"])
@jwt_required()
def delete_foto_profil(nim):
    """Hapus foto profil mahasiswa"""
    if current_user.role != "mahasiswa":
        return jsonify({"error": "Hanya mahasiswa yang dapat mengakses."}), 403
    
    mhs = Mahasiswa.query.get(nim)
    if not mhs:
        return jsonify({"error": "Mahasiswa tidak ditemukan."}), 404
    
    # Hapus file fisik
    if mhs.foto_profil:
        root_dir = os.path.dirname(current_app.root_path)
        file_path = os.path.join(root_dir, mhs.foto_profil)
        if os.path.exists(file_path):
            os.remove(file_path)
            print(f"🗑️ File foto dihapus: {file_path}")
    
    # Set foto_profil menjadi NULL
    mhs.foto_profil = None
    db.session.commit()
    
    return jsonify({
        "message": "Foto profil berhasil dihapus.",
        "foto_profil": None
    }), 200


# ============ REPLY CATATAN DOSEN WALI ============

@mahasiswa_bp.route("/catatan/<int:id_catatan>/reply", methods=["POST"])
@mahasiswa_required
def reply_catatan(id_catatan):
    """Mahasiswa membalas catatan dari dosen wali (hanya sekali)"""
    # Cek role mahasiswa
    if current_user.role != "mahasiswa":
        return jsonify({"error": "Hanya mahasiswa yang dapat membalas."}), 403
    
    # Ambil data catatan
    from app.models import CatatanKonseling
    catatan = CatatanKonseling.query.get(id_catatan)
    if not catatan:
        return jsonify({"error": "Catatan tidak ditemukan."}), 404
    
    # Cek apakah catatan milik mahasiswa ini
    if catatan.NIM != current_user.mahasiswa.NIM:
        return jsonify({"error": "Anda tidak dapat membalas catatan ini."}), 403
    
    # Cek apakah sudah pernah dibalas
    if catatan.reply:
        return jsonify({"error": "Anda sudah pernah membalas catatan ini."}), 400
    
    # Ambil isi balasan
    data = request.get_json(silent=True) or {}
    reply_text = data.get("reply", "").strip()
    
    if not reply_text:
        return jsonify({"error": "Balasan tidak boleh kosong."}), 400
    
    # Simpan balasan
    catatan.reply = reply_text
    catatan.tanggal_reply = datetime.utcnow()
    db.session.commit()
    
    return jsonify({
        "message": "Balasan berhasil dikirim.",
        "data": catatan.to_dict()
    }), 200

# ============ UPDATE REPLY CATATAN (EDIT) ============

@mahasiswa_bp.route("/catatan/<int:id_catatan>/reply", methods=["PUT"])
@mahasiswa_required
def update_reply_catatan(id_catatan):
    """Mahasiswa mengupdate balasan catatan dari dosen wali"""
    if current_user.role != "mahasiswa":
        return jsonify({"error": "Hanya mahasiswa yang dapat mengupdate balasan."}), 403
    
    from app.models import CatatanKonseling
    catatan = CatatanKonseling.query.get(id_catatan)
    if not catatan:
        return jsonify({"error": "Catatan tidak ditemukan."}), 404
    
    if catatan.NIM != current_user.mahasiswa.NIM:
        return jsonify({"error": "Anda tidak dapat mengupdate balasan catatan ini."}), 403
    
    if not catatan.reply:
        return jsonify({"error": "Belum ada balasan untuk diedit."}), 400
    
    data = request.get_json(silent=True) or {}
    reply_text = data.get("reply", "").strip()
    
    if not reply_text:
        return jsonify({"error": "Balasan tidak boleh kosong."}), 400
    
    # Update balasan
    catatan.reply = reply_text
    catatan.tanggal_reply = datetime.utcnow()
    db.session.commit()
    
    return jsonify({
        "message": "Balasan berhasil diperbarui.",
        "data": catatan.to_dict()
    }), 200

@mahasiswa_bp.route("/catatan/detail/<int:id_catatan>", methods=["GET"])
@jwt_required()
def detail_catatan(id_catatan):
    """Ambil detail catatan termasuk balasan"""
    from app.models import CatatanKonseling
    catatan = CatatanKonseling.query.get(id_catatan)
    if not catatan:
        return jsonify({"error": "Catatan tidak ditemukan."}), 404
    
    # Cek akses berdasarkan role
    if current_user.role == "mahasiswa" and catatan.NIM != current_user.mahasiswa.NIM:
        return jsonify({"error": "Akses ditolak."}), 403
    if current_user.role == "dosen" and catatan.NIP != current_user.dosen.NIP:
        return jsonify({"error": "Akses ditolak."}), 403
    
    return jsonify(catatan.to_dict()), 200

# ============ GET PROFIL DATA ============

@mahasiswa_bp.route("/profil/data/<nim>", methods=["GET"])
@jwt_required()
def get_profil_data(nim):
    """Ambil data lengkap profil mahasiswa"""
    if current_user.role == "mahasiswa" and current_user.mahasiswa.NIM != nim:
        return jsonify({"error": "Akses ditolak."}), 403
    
    mhs = Mahasiswa.query.get(nim)
    if not mhs:
        return jsonify({"error": "Mahasiswa tidak ditemukan."}), 404
    
    # Ambil nama jurusan dari tabel jurusan
    jurusan = ""
    if mhs.id_jurusan:
        from app.models import Jurusan
        jurusan_obj = Jurusan.query.filter_by(Id_Jurusan=mhs.id_jurusan).first()
        if jurusan_obj:
            jurusan = jurusan_obj.nama_jurusan
    
    # 🔥 TAMBAHKAN: Ambil data dosen wali
    nama_dosen_wali = ""
    nip_doswal = ""
    if mhs.NIP_doswal:
        from app.models import Dosen
        dosen_wali = Dosen.query.filter_by(NIP=mhs.NIP_doswal).first()
        if dosen_wali:
            nama_dosen_wali = dosen_wali.nama_dosen
            nip_doswal = dosen_wali.NIP
    
    return jsonify({
        "nim": mhs.NIM,
        "nama": mhs.nama_mahasiswa,
        "program": jurusan,
        "angkatan": mhs.angkatan or "",
        "kelas": mhs.kelas or "",
        "ipk": float(mhs.IPK) if mhs.IPK else None,
        "foto_profil": mhs.foto_profil,
        "gender": mhs.gender or "",
        "usia": mhs.usia,
        "freq_olahraga": mhs.freq_olahraga or "",
        "durasi_tidur": mhs.durasi_tidur or "",
        # 🔥 TAMBAHKAN: Data dosen wali
        "nip_doswal": nip_doswal,
        "nama_dosen_wali": nama_dosen_wali,
    }), 200