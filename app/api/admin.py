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
from datetime import datetime, timedelta
from functools import wraps

import pandas as pd
from flask import Blueprint, request, jsonify, send_file, current_app
from flask_jwt_extended import jwt_required, current_user
from sqlalchemy import func
from werkzeug.utils import secure_filename

from app.extensions import db
from app.models import (
    User, Mahasiswa, Dosen, RiwayatSkrining,
    MLModel, TrainingHistory, Dataset  # <-- tambahkan Dataset
)

admin_bp = Blueprint("admin", __name__)


# ── Auth guard ────────────────────────────────────────────────────
def admin_required(fn):
    @wraps(fn)
    @jwt_required()
    def wrapper(*args, **kwargs):
        if current_user.role != "admin":
            return jsonify({"error": "Hanya admin yang dapat mengakses endpoint ini."}), 403
        return fn(*args, **kwargs)
    return wrapper


# ── Dashboard stats ───────────────────────────────────────────────
@admin_bp.route("/dashboard-stats", methods=["GET"])
@admin_required
def dashboard_stats():
    total_mhs   = Mahasiswa.query.count()
    total_dosen = Dosen.query.count()
    total_skrining = RiwayatSkrining.query.count()

    sudah_skrining = db.session.query(func.count(func.distinct(RiwayatSkrining.NIM))).scalar()

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

    active_stress = MLModel.query.filter_by(type="stress",   is_active=True).first()
    active_motiv  = MLModel.query.filter_by(type="motivasi", is_active=True).first()

    return jsonify({
        "total_mahasiswa":  total_mhs,
        "total_dosen":      total_dosen,
        "total_skrining":   total_skrining,
        "sudah_skrining":   sudah_skrining,
        "belum_skrining":   total_mhs - sudah_skrining,
        "stress_dist":      stress_dist,
        "motivasi_dist":    motivasi_dist,
        "active_model_stress":   active_stress.to_dict()  if active_stress else None,
        "active_model_motivasi": active_motiv.to_dict()   if active_motiv  else None,
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
ALLOWED_EXTENSIONS = {'csv', 'xlsx'}
REQUIRED_COLUMNS = 75

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


@admin_bp.route("/datasets", methods=["GET"])
@admin_required
def list_datasets():
    """Mengembalikan daftar dataset yang pernah diunggah."""
    datasets = Dataset.query.order_by(Dataset.uploaded_at.desc()).all()
    return jsonify([d.to_dict() for d in datasets])


@admin_bp.route("/upload-dataset", methods=["POST"])
@admin_required
def upload_dataset():
    """
    Upload file CSV/Excel (75 kolom).
    Field form: file, type (opsional: stress/motivasi)
    """
    file = request.files.get("file")
    if not file:
        return jsonify({"error": "File tidak ditemukan"}), 400
    if not allowed_file(file.filename):
        return jsonify({"error": "Format file tidak didukung (hanya .csv, .xlsx)"}), 415

    # Simpan file sementara
    upload_folder = current_app.config.get("UPLOAD_FOLDER", "uploads/datasets")
    os.makedirs(upload_folder, exist_ok=True)
    filename = secure_filename(file.filename)
    # Tambahkan timestamp agar unik
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

    # Simpan record ke database
    dataset_type = request.form.get("type", None)
    dataset = Dataset(
        filename=filename,
        filepath=filepath,
        type=dataset_type,
        rows=len(df),
        columns=df.shape[1],
        uploaded_at=datetime.utcnow()
    )
    db.session.add(dataset)
    db.session.commit()

    return jsonify({
        "dataset_id": dataset.id,
        "filename": filename,
        "rows": dataset.rows,
        "columns": dataset.columns
    }), 201


# ── Retrain endpoint (JSON body) ─────────────────────────────────
@admin_bp.route("/retrain", methods=["POST"])
@admin_required
def retrain():
    """
    Trigger training baru dengan dataset yang sudah diunggah.
    Body JSON:
      type: "stress" | "motivasi"
      dataset_id: int
      hyperparams: (opsional) {
          strategy: "gridsearch" | "manual",
          params: { n_estimators, max_depth, ... }
      }
    """
    data = request.get_json()
    if not data:
        return jsonify({"error": "Body JSON diperlukan"}), 400

    model_type = data.get("type")
    dataset_id = data.get("dataset_id")
    if not model_type or not dataset_id:
        return jsonify({"error": "Field 'type' dan 'dataset_id' wajib"}), 400
    if model_type not in ("stress", "motivasi"):
        return jsonify({"error": "type harus 'stress' atau 'motivasi'"}), 400

    # Cek dataset
    dataset = Dataset.query.get(dataset_id)
    if not dataset:
        return jsonify({"error": "Dataset tidak ditemukan"}), 404

    hyperparams = data.get("hyperparams")  # bisa None

    # Buat record TrainingHistory
    task_id = str(uuid.uuid4())
    history = TrainingHistory(
        status="queued",
        task_id=task_id,
        dataset_filename=dataset.filename,
        data_size=dataset.rows,
        created_at=datetime.utcnow()
    )
    db.session.add(history)
    db.session.commit()

    # Ambil task Celery yang sudah terdaftar
    celery_task = current_app.extensions.get("celery_train_task")
    if not celery_task:
        # Fallback synchronous (seharusnya tidak terjadi di production)
        return jsonify({"error": "Celery task tidak tersedia"}), 503

    celery_task.apply_async(
        kwargs={
            "history_id": history.id,
            "csv_path": dataset.filepath,
            "model_type": model_type,
            "hyperparams": hyperparams,
            "models_folder": current_app.config["MODELS_FOLDER"],
        },
        task_id=task_id
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
    q    = TrainingHistory.query.order_by(TrainingHistory.created_at.desc())
    pag  = q.paginate(page=page, per_page=per, error_out=False)
    return jsonify({
        "data":        [h.to_dict() for h in pag.items],
        "total":       pag.total,
        "page":        pag.page,
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


# ── Data collector & export ──────────────────────────────────────
@admin_bp.route("/data-collector", methods=["GET"])
@admin_required
def data_collector():
    page    = request.args.get("page", 1, type=int)
    per     = request.args.get("per_page", 20, type=int)
    mtype   = request.args.get("type")
    angkatan= request.args.get("angkatan")
    jurusan = request.args.get("jurusan")
    level   = request.args.get("level")

    q = RiwayatSkrining.query.join(Mahasiswa)
    if level and mtype == "stress":
        q = q.filter(RiwayatSkrining.tingkat_stres == level)
    elif level and mtype == "motivasi":
        q = q.filter(RiwayatSkrining.tingkat_motivasi == level)

    pag = q.order_by(RiwayatSkrining.tanggal_skrining.desc()).paginate(
        page=page, per_page=per, error_out=False
    )

    rows = []
    for row in pag.items:
        d = row.to_dict()
        d["nama_mahasiswa"] = row.mahasiswa.nama_mahasiswa
        d["kelas"]          = row.mahasiswa.kelas
        rows.append(d)

    return jsonify({
        "data":        rows,
        "total":       pag.total,
        "page":        pag.page,
        "total_pages": pag.pages,
    })


@admin_bp.route("/export", methods=["GET"])
@admin_required
def export_data():
    """
    Ekspor data mentah kuesioner + demografi ke CSV/Excel.
    Query params:
      - format: 'csv' (default) atau 'excel'
      - angkatan, jurusan, start_date, end_date
    """
    fmt = request.args.get("format", "csv").lower()
    angkatan = request.args.get("angkatan")
    jurusan = request.args.get("jurusan")
    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")

    query = db.session.query(
        RiwayatSkrining,
        Mahasiswa,
        jurusan
    ).join(
        Mahasiswa, RiwayatSkrining.NIM == Mahasiswa.NIM
    ).join(
        jurusan, Mahasiswa.id_jurusan == jurusan.Id_jurusan, isouter=True
    )

    if angkatan:
        query = query.filter(Mahasiswa.angkatan == angkatan)
    if jurusan:
        query = query.filter(jurusan.nama_jurusan == jurusan)
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
    rows = []
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
        rows.append(row)

    if not rows:
        return jsonify({"error": "Tidak ada data yang cocok."}), 404

    df = pd.DataFrame(rows)
    column_order = (
        ["Jurusan", "Angkatan", "Gender", "Usia", "IPK",
         "freq_olahraga", "durasi_tidur"] +
        [f"S{i}" for i in range(1, 41)] +
        [f"M{i}" for i in range(1, 29)]
    )
    df = df[column_order]

    buf = io.BytesIO()
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

    if fmt == "excel":
        df.to_excel(buf, index=False, engine='openpyxl')
        buf.seek(0)
        return send_file(
            buf,
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            as_attachment=True,
            download_name=f"dataset_mindemy_{timestamp}.xlsx"
        )
    else:
        df.to_csv(buf, index=False)
        buf.seek(0)
        return send_file(
            buf,
            mimetype="text/csv",
            as_attachment=True,
            download_name=f"dataset_mindemy_{timestamp}.csv"
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