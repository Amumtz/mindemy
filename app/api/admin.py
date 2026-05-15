"""
blueprints/admin.py (app/api/admin.py)
───────────────────────────────────────────────
Endpoint administrator: statistik, manajemen model,
upload dataset, trigger training, monitoring.
"""

import os
import io
import json
import uuid
from datetime import datetime, timedelta, date
from functools import wraps

import pandas as pd
from flask import Blueprint, request, jsonify, send_file, current_app
from flask_jwt_extended import jwt_required, current_user
from sqlalchemy import func, cast, Date, distinct, extract
from werkzeug.utils import secure_filename
import calendar  

from app.extensions import db
from app.models import (
    User, Mahasiswa, Dosen, RiwayatSkrining,
    MLModel, TrainingHistory, Dataset,
    Jurusan  
)

admin_bp = Blueprint("admin", __name__)

ALLOWED_EXTENSIONS = {'csv', 'xlsx'}
REQUIRED_COLUMNS = 75

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# ── Auth guard ────────────────────────────────────────────────────
def admin_required(fn):
    @wraps(fn)
    @jwt_required()
    def wrapper(*args, **kwargs):
        if current_user.role != "admin":
            return jsonify({"error": "Hanya admin yang dapat mengakses endpoint ini."}), 403
        return fn(*args, **kwargs)
    return wrapper


# ── Dashboard stats (tambah total skrining hari ini) ─────────────
@admin_bp.route("/dashboard-stats", methods=["GET"])
@admin_required
def dashboard_stats():
    total_mhs   = Mahasiswa.query.count()
    total_dosen = Dosen.query.count()
    total_skrining = RiwayatSkrining.query.count()

    # Total skrining hari ini
    today = date.today()
    total_skrining_hari_ini = RiwayatSkrining.query.filter(
        cast(RiwayatSkrining.tanggal_skrining, Date) == today
    ).count()

    start_of_week = today - timedelta(days=today.weekday())

    total_skrining_minggu_ini = RiwayatSkrining.query.filter(
        cast(RiwayatSkrining.tanggal_skrining, Date) >= start_of_week
    ).count()

    # ── 2. Tren harian (7 hari terakhir) ──
    tujuh_hari_lalu = datetime.utcnow() - timedelta(days=7)

    daily_data = (
        db.session.query(
            cast(RiwayatSkrining.tanggal_skrining, Date).label("tgl"),
            func.avg(RiwayatSkrining.score_stress).label("avg_stress"),
            func.avg(RiwayatSkrining.score_sdi).label("avg_sdi")
        )
        .filter(RiwayatSkrining.tanggal_skrining >= tujuh_hari_lalu)
        .group_by("tgl")
        .order_by("tgl")
        .all()
    )

    daily_trend = [
        {
            "date": str(tgl),
            "avg_stress": round(float(avg_stress), 2) if avg_stress else 0,
            "avg_sdi": round(float(avg_sdi), 2) if avg_sdi else 0
        }
        for tgl, avg_stress, avg_sdi in daily_data
    ]

    sudah_skrining = db.session.query(func.count(func.distinct(RiwayatSkrining.NIM))).scalar()

    # Distribusi berdasarkan skrining terbaru tiap mahasiswa
    subq = (
        db.session.query(
            RiwayatSkrining.NIM,
            func.max(RiwayatSkrining.tanggal_skrining).label("max_tgl")
        ).group_by(RiwayatSkrining.NIM).subquery()
    )
    latest = (
        db.session.query(RiwayatSkrining)
        .join(subq, (RiwayatSkrining.NIM == subq.c.NIM) &
                    (RiwayatSkrining.tanggal_skrining == subq.c.max_tgl))
        .all()
    )

    stress_dist   = {"Rendah": 0, "Sedang": 0, "Tinggi": 0}
    motivasi_dist = {"Rendah": 0, "Sedang": 0, "Tinggi": 0}
    for row in latest:
        if row.tingkat_stres:    stress_dist[row.tingkat_stres]     += 1
        if row.tingkat_motivasi: motivasi_dist[row.tingkat_motivasi] += 1
    
        # ── 1. Distribusi per jurusan (mahasiswa sudah skrining) ──
    try:
        jurusan_query = (
            db.session.query(
                Jurusan.nama_jurusan,
                func.count(distinct(RiwayatSkrining.NIM)).label("jumlah")
            )
            .join(Mahasiswa, RiwayatSkrining.NIM == Mahasiswa.NIM)
            .join(Jurusan, Mahasiswa.id_jurusan == Jurusan.Id_Jurusan)  # perbaikan: Id_Jurusan # perbaikan: Id_Jurusan
            .group_by(Jurusan.nama_jurusan)
            .all()
        )
        jurusan_distribution = [{"jurusan": nama, "count": jumlah} for nama, jumlah in jurusan_query]
    except Exception as e:
        current_app.logger.error(f"Gagal query jurusan_distribution: {e}")
        jurusan_distribution = []

    # ── 2. Tren per bulan (6 bulan terakhir) ──
    try:
        # Ambil 6 bulan terakhir dari hari ini
        today = datetime.utcnow()
        start_date = today - timedelta(days=180)  # pendekatan cepat

        # Group by tahun + bulan (kompatibel semua database)
        daily_data = (
            db.session.query(
                extract('year', RiwayatSkrining.tanggal_skrining).label('tahun'),
                extract('month', RiwayatSkrining.tanggal_skrining).label('bulan'),
                func.avg(RiwayatSkrining.score_stress).label('avg_stress'),
                func.avg(RiwayatSkrining.score_sdi).label('avg_sdi')
            )
            .filter(RiwayatSkrining.tanggal_skrining >= start_date)
            .group_by('tahun', 'bulan')
            .order_by('tahun', 'bulan')
            .all()
        )

        daily_trend = []
        for tahun, bulan, avg_s, avg_sdi in daily_data:
            if tahun and bulan:
                bulan_str = f"{int(tahun)}-{int(bulan):02d}"
                daily_trend.append({
                    "date": bulan_str,
                    "avg_stress": round(float(avg_s), 2) if avg_s is not None else 0,
                    "avg_sdi": round(float(avg_sdi), 2) if avg_sdi is not None else 0
                })
    except Exception as e:
        current_app.logger.error(f"Gagal query daily_trend: {e}")
        daily_trend = []

    
    active_stress = MLModel.query.filter_by(type="stress",   is_active=True).first()
    active_motiv  = MLModel.query.filter_by(type="motivasi", is_active=True).first()

    return jsonify({
        "total_mahasiswa":  total_mhs,
        "total_dosen":      total_dosen,
        "total_skrining":   total_skrining,
        "total_skrining_minggu_ini": total_skrining_minggu_ini, 
        "total_skrining_hari_ini": total_skrining_hari_ini,   # <-- TAMBAHAN
        "sudah_skrining":   sudah_skrining,
        "belum_skrining":   total_mhs - sudah_skrining,
        "stress_dist":      stress_dist,
        "motivasi_dist":    motivasi_dist,
        "active_model_stress":   active_stress.to_dict()  if active_stress else None,
        "active_model_motivasi": active_motiv.to_dict()   if active_motiv  else None,
        "jurusan_distribution": jurusan_distribution,
        "daily_trend": daily_trend
    })


# ── Models CRUD ──────────────────────────────────────────────────
@admin_bp.route("/models", methods=["GET"])
@admin_required
def get_models():
    mtype = request.args.get("type")
    q = MLModel.query
    if mtype:
        q = q.filter_by(type=mtype)
    models = q.order_by(MLModel.created_at.desc()).all()
    return jsonify([m.to_dict() for m in models])


@admin_bp.route("/models/<int:model_id>/activate", methods=["POST"])
@admin_required
def activate_model(model_id: int):
    model = MLModel.query.get_or_404(model_id)
    MLModel.query.filter_by(type=model.type, is_active=True).update({"is_active": False})
    model.is_active = True
    db.session.commit()

    from app.ml.predictor import registry
    registry.load(model.type, model.file_path,
                  model.to_dict() | {"thresholds": model.get_thresholds()})
    return jsonify({"message": f"Model {model.algorithm} v{model.version} diaktifkan."})


@admin_bp.route("/models/<int:model_id>", methods=["DELETE"])
@admin_required
def delete_model(model_id: int):
    model = MLModel.query.get_or_404(model_id)
    if model.is_active:
        return jsonify({"error": "Tidak dapat menghapus model yang sedang aktif."}), 400
    if os.path.exists(model.file_path):
        os.remove(model.file_path)
    db.session.delete(model)
    db.session.commit()
    return jsonify({"message": "Model berhasil dihapus."})


# ── Dataset upload & list ────────────────────────────────────────


# @admin_bp.route("/datasets", methods=["GET"])
# @admin_required
# def list_datasets():
#     """Mengembalikan daftar dataset yang pernah diunggah."""
#     datasets = Dataset.query.order_by(Dataset.uploaded_at.desc()).all()
#     return jsonify([d.to_dict() for d in datasets])


# # @admin_bp.route("/upload-dataset", methods=["POST"])
# # @admin_required
# # def upload_dataset():
# #     """
# #     Upload file CSV/Excel (75 kolom).
# #     Field form: file, type (opsional: stress/motivasi)
# #     """
# #     file = request.files.get("file")
# #     if not file:
# #         return jsonify({"error": "File tidak ditemukan"}), 400
# #     if not allowed_file(file.filename):
# #         return jsonify({"error": "Format file tidak didukung (hanya .csv, .xlsx)"}), 415

# #     # Simpan file sementara
# #     upload_folder = current_app.config.get("UPLOAD_FOLDER", "uploads/datasets")
# #     os.makedirs(upload_folder, exist_ok=True)
# #     filename = secure_filename(file.filename)
# #     # Tambahkan timestamp agar unik
# #     unique_name = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:6]}_{filename}"
# #     filepath = os.path.join(upload_folder, unique_name)
# #     file.save(filepath)

# #     # Validasi jumlah kolom
# #     try:
# #         if filename.endswith('.csv'):
# #             df = pd.read_csv(filepath)
# #         else:
# #             df = pd.read_excel(filepath)
# #         if df.shape[1] != REQUIRED_COLUMNS:
# #             os.remove(filepath)
# #             return jsonify({"error": f"Dataset harus memiliki {REQUIRED_COLUMNS} kolom, ditemukan {df.shape[1]}"}), 400
# #     except Exception as e:
# #         os.remove(filepath)
# #         return jsonify({"error": f"Gagal membaca file: {str(e)}"}), 400

# #     # Simpan record ke database
# #     dataset_type = request.form.get("type", None)
# #     dataset = Dataset(
# #         filename=filename,
# #         filepath=filepath,
# #         type=dataset_type,
# #         rows=len(df),
# #         columns=df.shape[1],
# #         uploaded_at=datetime.utcnow()
# #     )
# #     db.session.add(dataset)
# #     db.session.commit()

# #     return jsonify({
# #         "dataset_id": dataset.id,
# #         "filename": filename,
# #         "rows": dataset.rows,
# #         "columns": dataset.columns
# #     }), 201


# ── Retrain endpoint (JSON body) ─────────────────────────────────
@admin_bp.route("/retrain", methods=["POST"])
@admin_required
def retrain():
    """
    Trigger training dengan file yang diunggah langsung.
    Form fields:
      file: file CSV/Excel (75 kolom)
      type: "stress" | "motivasi"
      hyperparams: JSON string (optional)
    """
    file = request.files.get("file")
    if not file:
        return jsonify({"error": "File tidak ditemukan"}), 400

    # Validasi extensi
    if not allowed_file(file.filename):
        return jsonify({"error": "Format file tidak didukung (hanya .csv, .xlsx)"}), 415

    model_type = request.form.get("type")
    if not model_type or model_type not in ("stress", "motivasi"):
        return jsonify({"error": "type harus 'stress' atau 'motivasi'"}), 400

    # Simpan file sementara
    upload_folder = current_app.config.get("UPLOAD_FOLDER", "storage/uploads")
    os.makedirs(upload_folder, exist_ok=True)
    filename = secure_filename(file.filename)
    unique_name = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:6]}_{filename}"
    filepath = os.path.join(upload_folder, unique_name)
    file.save(filepath)

    # Validasi jumlah kolom
    try:
        if filename.endswith('.csv'):
            df = pd.read_csv(filepath)
        else:
            df = pd.read_excel(filepath)
        if df.shape[1] != REQUIRED_COLUMNS:
            os.remove(filepath)
            return jsonify({"error": f"Dataset harus memiliki {REQUIRED_COLUMNS} kolom, ditemukan {df.shape[1]}"}), 400
    except Exception as e:
        os.remove(filepath)
        return jsonify({"error": f"Gagal membaca file: {str(e)}"}), 400

    # Hyperparams (optional)
    hyperparams = None
    hyperparams_str = request.form.get("hyperparams")
    if hyperparams_str:
        try:
            hyperparams = json.loads(hyperparams_str)
        except:
            pass

    # Buat record TrainingHistory
    task_id = str(uuid.uuid4())
    history = TrainingHistory(
        status="queued",
        task_id=task_id,
        dataset_filename=filename,
        data_size=len(df),
        created_at=datetime.utcnow()
    )
    db.session.add(history)
    db.session.commit()

    # Panggil Celery task (atau fallback sync)
    celery_task = current_app.extensions.get("celery_train_task")
    if celery_task:
        celery_task.apply_async(
            kwargs={
                "history_id": history.id,
                "csv_path": filepath,
                "model_type": model_type,
                "hyperparams": hyperparams,
                "models_folder": current_app.config["MODELS_FOLDER"],
            },
            task_id=task_id
        )
    else:
        # Fallback synchronous (untuk development)
        from app.tasks.training import train_model
        train_model(
            history_id=history.id,
            csv_path=filepath,
            model_type=model_type,
            hyperparams=hyperparams,
            models_folder=current_app.config["MODELS_FOLDER"]
        )

    return jsonify({
        "task_id": task_id,
        "history_id": history.id,
        "message": "Proses pelatihan telah dimasukkan ke antrian"
    }), 202

@admin_bp.route("/retrain-status", methods=["GET"])
@admin_required
def retrain_status():
    """
    Polling status training dari database.
    Parameter: task_id
    """
    task_id = request.args.get("task_id")
    if not task_id:
        return jsonify({"error": "task_id diperlukan"}), 400

    history = TrainingHistory.query.filter_by(task_id=task_id).first()
    if not history:
        return jsonify({"error": "Task tidak ditemukan"}), 404

    # Parse progress_message jika ada
    progress = 0
    message = ""
    if history.progress_message:
        try:
            prog = json.loads(history.progress_message)
            progress = prog.get("progress", 0)
            message = prog.get("message", "")
        except:
            pass

    return jsonify({
        "task_id": task_id,
        "status": history.status,
        "progress": progress,
        "message": message,
        "metrics": json.loads(history.metrics) if history.metrics else None,
    })


# ── Training history & status (Celery) ──────────────────────────
@admin_bp.route("/training-history", methods=["GET"])
@admin_required
def training_history():
    page = request.args.get("page", 1, type=int)
    per  = request.args.get("per_page", 15, type=int)
    status = request.args.get("status")
    search = request.args.get("search")
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")

    q = TrainingHistory.query

    if status:
        q = q.filter(TrainingHistory.status == status)
    if search:
        q = q.filter(TrainingHistory.dataset_filename.ilike(f"%{search}%"))
    if start_date:
        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            q = q.filter(TrainingHistory.created_at >= start_dt)
        except ValueError:
            pass
    if end_date:
        try:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
            q = q.filter(TrainingHistory.created_at < end_dt)
        except ValueError:
            pass

    q = q.order_by(TrainingHistory.created_at.desc())
    pag = q.paginate(page=page, per_page=per, error_out=False)

    # Perkaya dengan info model terkait
    data = []
    for h in pag.items:
        h_dict = h.to_dict()
        if h.model_id:
            model = MLModel.query.get(h.model_id)
            if model:
                h_dict["algorithm"] = model.algorithm
                h_dict["version"] = model.version
                h_dict["model_type"] = model.type
                h_dict["is_active"] = model.is_active
            else:
                h_dict["algorithm"] = None
                h_dict["version"] = None
                h_dict["model_type"] = None
                h_dict["is_active"] = False
        else:
            h_dict["algorithm"] = None
            h_dict["version"] = None
            h_dict["model_type"] = None
            h_dict["is_active"] = False
        data.append(h_dict)

    return jsonify({
        "data": data,
        "total": pag.total,
        "page": pag.page,
        "total_pages": pag.pages,
    })

@admin_bp.route("/training-status/<task_id>", methods=["GET"])
@admin_required
def training_status(task_id: str):
    """
    Status langsung dari Celery (untuk debug).
    """
    task = current_app.extensions.get("celery_train_task")
    if task is None:
        return jsonify({"error": "Celery tidak tersedia."}), 503

    result = task.AsyncResult(task_id)
    info   = result.info or {}
    return jsonify({
        "task_id": task_id,
        "state":   result.state,
        "info":    info if isinstance(info, dict) else {"error": str(info)},
    })


# ── Data collector (tambah filter jurusan & angkatan) ────────────
@admin_bp.route("/data-collector", methods=["GET"])
@admin_required
def data_collector():
    page     = request.args.get("page", 1, type=int)
    per      = request.args.get("per_page", 20, type=int)
    mtype    = request.args.get("type")
    angkatan = request.args.get("angkatan")
    jurusan_nama = request.args.get("jurusan")
    level    = request.args.get("level")
    search   = request.args.get("search", "")

    # Base query
    q = db.session.query(RiwayatSkrining, Mahasiswa, Jurusan).join(
        Mahasiswa, RiwayatSkrining.NIM == Mahasiswa.NIM
    ).join(
        Jurusan, Mahasiswa.id_jurusan == Jurusan.Id_Jurusan, isouter=True
    )

    # Terapkan filter
    if level and mtype == "stress":
        q = q.filter(RiwayatSkrining.tingkat_stres == level)
    elif level and mtype == "motivasi":
        q = q.filter(RiwayatSkrining.tingkat_motivasi == level)
    if angkatan:
        q = q.filter(Mahasiswa.angkatan == angkatan)
    if jurusan_nama:
        q = q.filter(Jurusan.nama_jurusan == jurusan_nama)
    if search:
        q = q.filter(
            (Mahasiswa.nama_mahasiswa.ilike(f"%{search}%")) |
            (Mahasiswa.NIM.ilike(f"%{search}%"))
        )

    # Hitung statistik cards (berdasarkan filter yang sama)
    total_filtered = q.count()
    today = date.today()
    today_filtered = q.filter(cast(RiwayatSkrining.tanggal_skrining, Date) == today).count()
    agg = q.with_entities(
        func.avg(RiwayatSkrining.score_stress).label("avg_stress"),
        func.avg(RiwayatSkrining.score_sdi).label("avg_sdi")
    ).first()
    avg_stress = round(float(agg.avg_stress), 1) if agg and agg.avg_stress else 0
    avg_motivasi = round(float(agg.avg_sdi), 1) if agg and agg.avg_sdi else 0

    # Paginasi
    pag = q.order_by(RiwayatSkrining.tanggal_skrining.desc()).paginate(
        page=page, per_page=per, error_out=False
    )

    # Bentuk data baris
    rows = []
    for (skrining, mhs, jur) in pag.items:
        jawaban = skrining.get_jawaban()
        stress_scores = [jawaban.get(f"S{i}", 0) for i in range(1, 41)]
        motivasi_scores = [jawaban.get(f"M{i}", 0) for i in range(1, 29)]
        rows.append({
            "Id_skrining": skrining.Id_skrining,
            "NIM": skrining.NIM,
            "nama_mahasiswa": mhs.nama_mahasiswa,
            "jurusan": jur.nama_jurusan if jur else "",
            "angkatan": mhs.angkatan or "",
            "gender": mhs.gender or "",
            "usia": mhs.usia or "",
            "kelas": mhs.kelas or "",
            "IPK": float(mhs.IPK) if mhs.IPK else 0,
            "freq_olahraga": mhs.freq_olahraga or "",
            "durasi_tidur": mhs.durasi_tidur or "",
            "tanggal_skrining": skrining.tanggal_skrining.isoformat() if skrining.tanggal_skrining else None,
            "tingkat_stres": skrining.tingkat_stres,
            "tingkat_motivasi": skrining.tingkat_motivasi,
            "score_stress": skrining.score_stress,
            "score_sdi": skrining.score_sdi,
            "stress_scores": stress_scores,
            "motivasi_scores": motivasi_scores,
        })

    return jsonify({
        "data": rows,
        "total": total_filtered,
        "today_total": today_filtered,
        "avg_stress": avg_stress,
        "avg_motivasi": avg_motivasi,
        "page": pag.page,
        "total_pages": pag.pages,
    })


# ── Export data (perbaiki join Jurusan) ──────────────────────────
@admin_bp.route("/export", methods=["GET"])
@admin_required
def export_data():
    fmt = request.args.get("format", "csv").lower()
    angkatan = request.args.get("angkatan")
    jurusan_nama = request.args.get("jurusan")
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")

    # ── 1. Ambil data dari database (sama seperti sebelumnya) ──
    query = db.session.query(
        RiwayatSkrining,
        Mahasiswa,
        Jurusan
    ).join(
        Mahasiswa, RiwayatSkrining.NIM == Mahasiswa.NIM
    ).join(
        Jurusan, Mahasiswa.id_jurusan == Jurusan.Id_Jurusan, isouter=True
    )

    if angkatan:
        query = query.filter(Mahasiswa.angkatan == angkatan)
    if jurusan_nama:
        query = query.filter(Jurusan.nama_jurusan == jurusan_nama)
    if start_date:
        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
            query = query.filter(RiwayatSkrining.tanggal_skrining >= start_dt)
        except ValueError:
            return jsonify({"error": "Format start_date harus YYYY-MM-DD"}), 400
    if end_date:
        try:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1)
            query = query.filter(RiwayatSkrining.tanggal_skrining < end_dt)
        except ValueError:
            return jsonify({"error": "Format end_date harus YYYY-MM-DD"}), 400

    results = query.all()
    db_rows = []
    for skrining, mhs, jur in results:
        jawaban = skrining.get_jawaban()
        row = {
            "Jurusan": jur.nama_jurusan if jur else "",
            "Angkatan": mhs.angkatan or "",
            "Gender": mhs.gender or "",
            "Usia": mhs.usia or "",
            "IPK": mhs.IPK or "",
            "freq_olahraga": mhs.freq_olahraga or "",
            "durasi_tidur": mhs.durasi_tidur or "",
        }
        for i in range(1, 41):
            row[f"S{i}"] = jawaban.get(f"S{i}", 0)
        for i in range(1, 29):
            row[f"M{i}"] = jawaban.get(f"M{i}", 0)
        db_rows.append(row)

    df_db = pd.DataFrame(db_rows)

    # ── 2. Baca dataset asli (DATA_LATIH.xlsx) ──
    #    Sesuaikan path absolut atau relatif terhadap project root
    initial_dataset_path = os.path.join(
        current_app.root_path, "..", "storage", "dataset", "DATA_LATIH.xlsx"
    )
    df_initial = pd.DataFrame()
    try:
        df_initial = pd.read_excel(initial_dataset_path)
        # Pastikan hanya ambil kolom yang diperlukan (sama seperti di atas)
        required_cols = ["Jurusan", "Angkatan", "Gender", "Usia", "IPK",
                         "freq_olahraga", "durasi_tidur"] + \
                        [f"S{i}" for i in range(1, 41)] + \
                        [f"M{i}" for i in range(1, 29)]
        # Filter kolom yang ada di dataset asli (jika ada yang kurang, isi 0)
        for col in required_cols:
            if col not in df_initial.columns:
                df_initial[col] = 0
        df_initial = df_initial[required_cols]

        # Terapkan filter angkatan & jurusan ke dataset asli juga
        if angkatan:
            # Pastikan tipe data cocok (mungkin string)
            df_initial = df_initial[df_initial["Angkatan"].astype(str) == str(angkatan)]
        if jurusan_nama:
            df_initial = df_initial[df_initial["Jurusan"].astype(str) == str(jurusan_nama)]
    except Exception as e:
        current_app.logger.warning(f"Gagal membaca dataset asli: {e}")
        # Lanjutkan tanpa dataset asli jika gagal

    # ── 3. Gabungkan kedua DataFrame ──
    df_merged = pd.concat([df_initial, df_db], ignore_index=True)

    # Jika tidak ada data sama sekali
    if df_merged.empty:
        return jsonify({"error": "Tidak ada data yang cocok."}), 404

    # Urutkan kolom sesuai format yang diinginkan
    column_order = (
        ["Jurusan", "Angkatan", "Gender", "Usia", "IPK",
         "freq_olahraga", "durasi_tidur"] +
        [f"S{i}" for i in range(1, 41)] +
        [f"M{i}" for i in range(1, 29)]
    )
    df_merged = df_merged[column_order]

    # ── 4. Kirim sebagai file ──
    buf = io.BytesIO()
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

    if fmt == "excel":
        df_merged.to_excel(buf, index=False, engine='openpyxl');
        buf.seek(0)
        return send_file(
            buf,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=f"dataset_gabungan_{timestamp}.xlsx"
        )
    else:  # default csv
        df_merged.to_csv(buf, index=False)
        buf.seek(0)
        return send_file(
            buf,
            mimetype="text/csv",
            as_attachment=True,
            download_name=f"dataset_gabungan_{timestamp}.csv"
        )


# ── Model loaded in memory (registry) ────────────────────────────
@admin_bp.route("/loaded-models", methods=["GET"])
@admin_required
def loaded_models():
    from app.ml.predictor import registry
    result = {}
    for model_type in ["stress", "motivasi"]:
        if registry.is_loaded(model_type):
            meta = registry.get_metadata(model_type)
            bundle = registry._bundles.get(model_type, {})
            result[model_type] = {
                "loaded": True,
                "algorithm": meta.get("algorithm"),
                "version": meta.get("version"),
                "accuracy": meta.get("accuracy"),
                "feature_count": len(bundle.get("feature_names", [])),
                "file_path": meta.get("file_path"),
                "thresholds": meta.get("thresholds"),
            }
        else:
            result[model_type] = {"loaded": False}
    return jsonify(result)