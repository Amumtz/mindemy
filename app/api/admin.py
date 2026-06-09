"""
blueprints/admin.py (app/api/admin.py)
───────────────────────────────────────────────
Endpoint administrator: statistik, manajemen model,
upload dataset, trigger training, monitoring,
manajemen mahasiswa & dosen (CRUD).
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
            .join(Jurusan, Mahasiswa.id_jurusan == Jurusan.Id_Jurusan)
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
        "total_skrining_hari_ini": total_skrining_hari_ini,
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
    model = MLModel.query.get(model_id)
    if model is None:
        return jsonify({"error": "Model tidak ditemukan."}), 404

    # Nonaktifkan semua model lain dengan tipe yang sama
    MLModel.query.filter_by(type=model.type, is_active=True).update({"is_active": False})
    
    # Aktifkan model yang dipilih
    model.is_active = True
    db.session.commit()

    # Muat model ke registry (jika file tersedia)
    from app.ml.predictor import registry
    try:
        registry.load(model.type, model.file_path,
                      model.to_dict() | {"thresholds": model.get_thresholds()})
    except Exception as e:
        # Rollback aktivasi jika load gagal, agar tidak terjadi ketidakcocokan
        db.session.rollback()
        return jsonify({"error": f"Gagal memuat model: {str(e)}"}), 500

    return jsonify({"message": f"Model {model.algorithm} v{model.version} berhasil diaktifkan."})


@admin_bp.route("/models/<int:model_id>", methods=["DELETE"])
@admin_required
def delete_model(model_id: int):
    model = MLModel.query.get_or_404(model_id)
    if model.is_active:
        return jsonify({"error": "Tidak dapat menghapus model yang sedang aktif."}), 400

    # Cari file .joblib dengan beberapa kemungkinan path (sama seperti download)
    possible_paths = [
        os.path.join(os.getcwd(), model.file_path),
        model.file_path,
        os.path.join(current_app.root_path, model.file_path),
        os.path.join(os.path.dirname(current_app.root_path), model.file_path),
        os.path.abspath(model.file_path)
    ]
    for p in possible_paths:
        if os.path.exists(p):
            try:
                os.remove(p)
                current_app.logger.info(f"File model dihapus: {p}")
            except Exception as e:
                current_app.logger.error(f"Gagal menghapus file {p}: {e}")
            break

    db.session.delete(model)
    db.session.commit()
    return jsonify({"message": "Model berhasil dihapus."})

@admin_bp.route("/models/<int:model_id>/download", methods=["GET"])
@admin_required
def download_model(model_id: int):
    model = MLModel.query.get(model_id)
    if not model:
        return jsonify({"error": "Model tidak ditemukan."}), 404

    if not model.file_path:
        return jsonify({"error": "Model tidak memiliki file tersimpan."}), 404

    # Mungkin file disimpan relatif terhadap folder backend (tempat flask run)
    # atau absolut. Kita coba beberapa path.
    possible_paths = [
        os.path.join(os.getcwd(), model.file_path),                      # relatif dari working directory
        model.file_path,                                                  # path asli (mungkin absolut)
        os.path.join(current_app.root_path, model.file_path),            # relatif dari app/
        os.path.join(os.path.dirname(current_app.root_path), model.file_path),  # relatif dari parent app/ (backend/)
        os.path.abspath(model.file_path)                                 # absolut
    ]

    file_path = None
    for p in possible_paths:
        current_app.logger.info(f"Mencoba path: {p}")
        if os.path.exists(p):
            file_path = p
            break

    if not file_path:
        current_app.logger.error(f"File model tidak ditemukan. Path dicoba: {possible_paths}")
        return jsonify({"error": "File model tidak ditemukan di server."}), 404

    download_name = os.path.basename(file_path)
    if not download_name.endswith('.joblib'):
        download_name += '.joblib'

    return send_file(
        file_path,
        as_attachment=True,
        download_name=download_name,
        mimetype='application/octet-stream'
    )


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
            "usia": mhs.usia if mhs.usia else (mhs.usia if hasattr(mhs, 'usia') else None),
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
            "Usia": mhs.usia if hasattr(mhs, 'usia') else (mhs.usia if mhs.tanggal_lahir else ""),
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

    initial_dataset_path = os.path.join(
        current_app.root_path, "..", "storage", "dataset", "DATA_LATIH.xlsx"
    )
    df_initial = pd.DataFrame()
    try:
        df_initial = pd.read_excel(initial_dataset_path)
        required_cols = ["Jurusan", "Angkatan", "Gender", "Usia", "IPK",
                         "freq_olahraga", "durasi_tidur"] + \
                        [f"S{i}" for i in range(1, 41)] + \
                        [f"M{i}" for i in range(1, 29)]
        for col in required_cols:
            if col not in df_initial.columns:
                df_initial[col] = 0
        df_initial = df_initial[required_cols]

        if angkatan:
            df_initial = df_initial[df_initial["Angkatan"].astype(str) == str(angkatan)]
        if jurusan_nama:
            df_initial = df_initial[df_initial["Jurusan"].astype(str) == str(jurusan_nama)]
    except Exception as e:
        current_app.logger.warning(f"Gagal membaca dataset asli: {e}")

    df_merged = pd.concat([df_initial, df_db], ignore_index=True)

    if df_merged.empty:
        return jsonify({"error": "Tidak ada data yang cocok."}), 404

    column_order = (
        ["Jurusan", "Angkatan", "Gender", "Usia", "IPK",
         "freq_olahraga", "durasi_tidur"] +
        [f"S{i}" for i in range(1, 41)] +
        [f"M{i}" for i in range(1, 29)]
    )
    df_merged = df_merged[column_order]

    buf = io.BytesIO()
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

    if fmt == "excel":
        df_merged.to_excel(buf, index=False, engine='openpyxl')
        buf.seek(0)
        return send_file(
            buf,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=f"dataset_gabungan_{timestamp}.xlsx"
        )
    else:
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


# ============ CRUD DOSEN ============
@admin_bp.route('/dosen/add', methods=['POST'])
@jwt_required()
def create_dosen():
    if current_user.role != 'admin':
        return jsonify({"error": "Hanya admin yang dapat mengakses"}), 403

    data = request.get_json()
    nip = data.get('nip')
    nama = data.get('nama')
    username = data.get('username')
    password = data.get('password')
    jabatan = data.get('jabatan', '')

    if not all([nip, nama, username, password]):
        return jsonify({"error": "NIP, nama, username, password wajib diisi"}), 400

    if User.query.filter_by(username=username).first():
        return jsonify({"error": "Username sudah digunakan"}), 409
    if Dosen.query.filter_by(NIP=nip).first():
        return jsonify({"error": "NIP sudah terdaftar"}), 409

    user = User(username=username, role='dosen')
    user.set_password(password)
    db.session.add(user)
    db.session.flush()

    dosen = Dosen(NIP=nip, nama_dosen=nama, jabatan=jabatan, Id_User=user.Id_User)
    db.session.add(dosen)
    db.session.commit()

    return jsonify({
        "message": "Dosen berhasil ditambahkan",
        "nip": nip,
        "username": username,
        "jabatan": jabatan
    }), 201

@admin_bp.route('/dosen/all', methods=['GET'])
@jwt_required()
def get_all_dosen():
    if current_user.role != 'admin':
        return jsonify({"error": "Admin only"}), 403

    dosen_list = Dosen.query.all()
    result = [{
        "nip": d.NIP,
        "nama": d.nama_dosen,
        "jabatan": d.jabatan or ""
    } for d in dosen_list]
    return jsonify(result), 200

@admin_bp.route('/dosen/<nip>', methods=['GET'])
@jwt_required()
def get_dosen(nip):
    if current_user.role != 'admin':
        return jsonify({"error": "Admin only"}), 403
    dsn = Dosen.query.filter_by(NIP=nip).first()
    if not dsn:
        return jsonify({"error": "Dosen tidak ditemukan"}), 404
    return jsonify({
        "nip": dsn.NIP,
        "nama": dsn.nama_dosen,
        "jabatan": dsn.jabatan or "",
        "username": dsn.user.username if dsn.user else None,
    }), 200

@admin_bp.route('/dosen/<nip>', methods=['PUT'])
@jwt_required()
def update_dosen(nip):
    if current_user.role != 'admin':
        return jsonify({"error": "Admin only"}), 403

    dsn = Dosen.query.filter_by(NIP=nip).first()
    if not dsn:
        return jsonify({"error": "Dosen tidak ditemukan"}), 404

    data = request.get_json(silent=True) or {}
    if 'nama' in data:
        dsn.nama_dosen = data['nama']
    if 'jabatan' in data:
        dsn.jabatan = data['jabatan']
    # Username/password bisa diubah melalui endpoint user khusus jika diperlukan
    db.session.commit()
    return jsonify({"message": "Profil dosen berhasil diperbarui"}), 200

@admin_bp.route('/dosen/<nip>', methods=['DELETE'])
@jwt_required()
def delete_dosen(nip):
    if current_user.role != 'admin':
        return jsonify({"error": "Admin only"}), 403
    dsn = Dosen.query.filter_by(NIP=nip).first()
    if not dsn:
        return jsonify({"error": "Dosen tidak ditemukan"}), 404
    user = dsn.user
    db.session.delete(dsn)
    if user:
        db.session.delete(user)
    db.session.commit()
    return jsonify({"message": "Dosen dan akunnya berhasil dihapus"}), 200


# ============ CRUD MAHASISWA ============
@admin_bp.route('/mahasiswa/add', methods=['POST'])
@jwt_required()
def create_mahasiswa():
    if current_user.role != 'admin':
        return jsonify({"error": "Hanya admin yang dapat mengakses"}), 403

    data = request.get_json()
    nim = data.get('nim')
    nama = data.get('nama')
    username = data.get('username')
    password = data.get('password')
    nip_dosen_wali = data.get('nip_dosen_wali')

    if not all([nim, nama, username, password, nip_dosen_wali]):
        return jsonify({"error": "NIM, nama, username, password, dan nip_dosen_wali wajib diisi"}), 400

    if User.query.filter_by(username=username).first():
        return jsonify({"error": "Username sudah digunakan"}), 409
    if Mahasiswa.query.filter_by(NIM=nim).first():
        return jsonify({"error": "NIM sudah terdaftar"}), 409

    dosen_wali = Dosen.query.filter_by(NIP=nip_dosen_wali).first()
    if not dosen_wali:
        return jsonify({"error": "Dosen wali dengan NIP tersebut tidak ditemukan"}), 404

    # Field tambahan untuk profil mahasiswa
    kelas = data.get('kelas')
    id_jurusan = data.get('id_jurusan')
    ipk = data.get('IPK')
    angkatan = data.get('angkatan')
    gender = data.get('gender')
    tanggal_lahir_str = data.get('tanggal_lahir')  # format YYYY-MM-DD

    # Parse tanggal lahir jika disertakan
    tanggal_lahir = None
    if tanggal_lahir_str:
        try:
            tanggal_lahir = datetime.strptime(tanggal_lahir_str, '%Y-%m-%d').date()
        except ValueError:
            return jsonify({"error": "Format tanggal_lahir harus YYYY-MM-DD"}), 400

    user = User(username=username, role='mahasiswa')
    user.set_password(password)
    db.session.add(user)
    db.session.flush()

    mhs = Mahasiswa(
        NIM=nim,
        nama_mahasiswa=nama,
        Id_User=user.Id_User,
        NIP_doswal=nip_dosen_wali,
        kelas=kelas,
        id_jurusan=id_jurusan,
        IPK=float(ipk) if ipk else None,
        angkatan=angkatan,
        gender=gender,
        tanggal_lahir=tanggal_lahir
    )
    db.session.add(mhs)
    db.session.commit()

    return jsonify({
        "message": "Mahasiswa berhasil ditambahkan",
        "nim": nim,
        "username": username,
        "dosen_wali": dosen_wali.nama_dosen
    }), 201

@admin_bp.route('/mahasiswa/all', methods=['GET'])
@jwt_required()
def get_all_mahasiswa():
    if current_user.role != 'admin':
        return jsonify({"error": "Admin only"}), 403

    mahasiswa_list = Mahasiswa.query.all()
    result = []
    for m in mahasiswa_list:
        dosen_wali = Dosen.query.filter_by(NIP=m.NIP_doswal).first() if m.NIP_doswal else None
        result.append({
            "nim": m.NIM,
            "nama": m.nama_mahasiswa,
            "username": m.user.username if m.user else None,
            "dosen_wali": dosen_wali.nama_dosen if dosen_wali else None,
            "nip_dosen_wali": m.NIP_doswal,
            "kelas": m.kelas or "",
            "id_jurusan": m.id_jurusan,
            "IPK": float(m.IPK) if m.IPK else None,
            "angkatan": m.angkatan or "",
            "gender": m.gender or "",
            "tanggal_lahir": m.tanggal_lahir.isoformat() if m.tanggal_lahir else None,
            "usia": m.usia if hasattr(m, 'usia') else (m.usia if m.tanggal_lahir else None),
        })
    return jsonify(result), 200

@admin_bp.route('/mahasiswa/<nim>', methods=['GET'])
@jwt_required()
def get_mahasiswa(nim):
    if current_user.role != 'admin':
        return jsonify({"error": "Admin only"}), 403
    mhs = Mahasiswa.query.filter_by(NIM=nim).first()
    if not mhs:
        return jsonify({"error": "Mahasiswa tidak ditemukan"}), 404

    dosen_wali = Dosen.query.filter_by(NIP=mhs.NIP_doswal).first() if mhs.NIP_doswal else None
    return jsonify({
        "nim": mhs.NIM,
        "nama": mhs.nama_mahasiswa,
        "kelas": mhs.kelas or "",
        "id_jurusan": mhs.id_jurusan,
        "IPK": float(mhs.IPK) if mhs.IPK else None,
        "NIP_doswal": mhs.NIP_doswal,
        "dosen_wali": dosen_wali.nama_dosen if dosen_wali else "",
        "angkatan": mhs.angkatan or "",
        "gender": mhs.gender or "",
        "tanggal_lahir": mhs.tanggal_lahir.isoformat() if mhs.tanggal_lahir else None,
        "usia": mhs.usia if hasattr(mhs, 'usia') else (mhs.usia if mhs.tanggal_lahir else None),
        "username": mhs.user.username if mhs.user else None,
    }), 200

@admin_bp.route('/mahasiswa/<nim>', methods=['PUT'])
@jwt_required()
def update_mahasiswa(nim):
    if current_user.role != 'admin':
        return jsonify({"error": "Admin only"}), 403

    mhs = Mahasiswa.query.filter_by(NIM=nim).first()
    if not mhs:
        return jsonify({"error": "Mahasiswa tidak ditemukan"}), 404

    data = request.get_json(silent=True) or {}

    if 'nama' in data:
        mhs.nama_mahasiswa = data['nama']
    if 'kelas' in data:
        mhs.kelas = data['kelas']
    if 'id_jurusan' in data:
        mhs.id_jurusan = data['id_jurusan']
    if 'IPK' in data:
        try:
            mhs.IPK = float(data['IPK'])
        except (TypeError, ValueError):
            return jsonify({"error": "IPK harus berupa angka"}), 400
    if 'angkatan' in data:
        mhs.angkatan = data['angkatan']
    if 'gender' in data:
        mhs.gender = data['gender']
    if 'tanggal_lahir' in data:
        try:
            mhs.tanggal_lahir = datetime.strptime(data['tanggal_lahir'], '%Y-%m-%d').date()
        except ValueError:
            return jsonify({"error": "Format tanggal_lahir harus YYYY-MM-DD"}), 400
    if 'nip_dosen_wali' in data:
        dosen = Dosen.query.filter_by(NIP=data['nip_dosen_wali']).first()
        if not dosen:
            return jsonify({"error": "Dosen wali dengan NIP tersebut tidak ditemukan"}), 404
        mhs.NIP_doswal = data['nip_dosen_wali']

    db.session.commit()
    return jsonify({"message": "Profil mahasiswa berhasil diperbarui"}), 200

@admin_bp.route('/mahasiswa/<nim>', methods=['DELETE'])
@jwt_required()
def delete_mahasiswa(nim):
    if current_user.role != 'admin':
        return jsonify({"error": "Admin only"}), 403
    mhs = Mahasiswa.query.filter_by(NIM=nim).first()
    if not mhs:
        return jsonify({"error": "Mahasiswa tidak ditemukan"}), 404
    user = mhs.user
    db.session.delete(mhs)
    if user:
        db.session.delete(user)
    db.session.commit()
    return jsonify({"message": "Mahasiswa dan akunnya berhasil dihapus"}), 200

@admin_bp.route('/jurusan/all', methods=['GET'])
@jwt_required()
def get_all_jurusan():
    # Admin atau dosen/mahasiswa bisa akses
    jurusan_list = Jurusan.query.order_by(Jurusan.nama_jurusan).all()
    result = [{
        "id": j.Id_Jurusan,
        "nama": j.nama_jurusan,
        "kaprodi": j.NIP_kaprodi or ""
    } for j in jurusan_list]
    return jsonify(result), 200