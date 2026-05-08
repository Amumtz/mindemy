# models/ml_model.py
import json
import joblib
import os
import numpy as np
from datetime import datetime
from app.extensions import db


def _convert_to_json_serializable(obj):
    """
    Konversi object yang tidak JSON-serializable (seperti numpy array)
    menjadi format yang bisa di-serialize.
    """
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    elif isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, np.floating):
        return float(obj)
    elif isinstance(obj, dict):
        return {k: _convert_to_json_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [_convert_to_json_serializable(item) for item in obj]
    return obj


# ───────────────────────────────────────
# MODEL DATASET (untuk upload file)
# ───────────────────────────────────────
class Dataset(db.Model):
    __tablename__ = "datasets"
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    filepath = db.Column(db.String(500), nullable=False)
    type = db.Column(db.String(50), nullable=True)
    rows = db.Column(db.Integer)
    columns = db.Column(db.Integer)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "filename": self.filename,
            "type": self.type,
            "rows": self.rows,
            "columns": self.columns,
            "uploaded_at": self.uploaded_at.isoformat() if self.uploaded_at else None,
        }


# ───────────────────────────────────────
# MODEL MLModel (model produksi)
# ───────────────────────────────────────
class MLModel(db.Model):
    __tablename__ = "models"

    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.Enum("stress", "motivasi"), nullable=False)
    algorithm = db.Column(db.String(50), nullable=False)
    version = db.Column(db.String(20), nullable=False)
    accuracy = db.Column(db.Float)
    precision_score = db.Column(db.Float)
    recall_score = db.Column(db.Float)
    f1_score = db.Column(db.Float)
    file_path = db.Column(db.String(255), nullable=False)
    is_active = db.Column(db.Boolean, default=False)
    data_count = db.Column(db.Integer)
    qcut_thresholds = db.Column(db.Text)          # JSON (deprecated, bisa tetap ada)
    artifact_metadata = db.Column(db.Text)        # JSON - Menyimpan bins, categories, best_params, cv_f1
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Relasi ke training history (opsional)
    training_history = db.relationship("TrainingHistory", back_populates="model")

    def get_thresholds(self) -> dict:
        """Backward compatible: ambil threshold dari qcut_thresholds atau artifact_metadata."""
        if self.qcut_thresholds:
            return json.loads(self.qcut_thresholds)
        # fallback ke artifact_metadata
        meta = self.get_artifact_metadata()
        return meta.get("thresholds", {})

    def get_artifact_metadata(self) -> dict:
        """Mengembalikan artifact metadata (bins, categories, best_params, cv_f1, dll)."""
        if self.artifact_metadata:
            return json.loads(self.artifact_metadata)
        return {}

    def set_artifact_metadata(self, metadata: dict):
        """Set artifact metadata, otomatis konversi ke JSON-serializable."""
        serializable_metadata = _convert_to_json_serializable(metadata)
        self.artifact_metadata = json.dumps(serializable_metadata)

    def load_artifact(self) -> dict:
        """
        Load artifact bundle dari file .joblib.
        Mengembalikan dictionary dengan: pipeline, feature_names, label_map,
        bins_stress, bins_motivasi, demo_categories, best_params, cv_macro_f1.
        """
        if not os.path.exists(self.file_path):
            raise FileNotFoundError(f"Model file tidak ditemukan: {self.file_path}")

        artifact = joblib.load(self.file_path)

        required_fields = ['pipeline', 'feature_names', 'label_map']
        for field in required_fields:
            if field not in artifact:
                raise ValueError(f"Artifact tidak memiliki field wajib: '{field}'")

        return artifact

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "algorithm": self.algorithm,
            "version": self.version,
            "accuracy": self.accuracy,
            "precision_score": self.precision_score,
            "recall_score": self.recall_score,
            "f1_score": self.f1_score,
            "file_path": self.file_path,
            "is_active": self.is_active,
            "data_count": self.data_count,
            "thresholds": self.get_thresholds(),
            "artifact_metadata": self.get_artifact_metadata(),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ───────────────────────────────────────
# MODEL TrainingHistory (log pelatihan)
# ───────────────────────────────────────
class TrainingHistory(db.Model):
    __tablename__ = "training_history"

    id = db.Column(db.Integer, primary_key=True)
    model_id = db.Column(db.Integer, db.ForeignKey("models.id"), nullable=True)
    data_size = db.Column(db.Integer, nullable=True)
    duration = db.Column(db.Float, nullable=True)         # detik (float)
    status = db.Column(
        db.Enum("queued", "running", "completed", "failed"),
        default="queued",
        nullable=False
    )
    error_message = db.Column(db.Text, nullable=True)
    metrics = db.Column(db.Text, nullable=True)           # JSON string
    progress_message = db.Column(db.Text, nullable=True)  # JSON {progress, message}
    dataset_filename = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    task_id = db.Column(db.String(100), nullable=True)    # ID Celery task / UUID

    model = db.relationship("MLModel", back_populates="training_history")

    def get_metrics(self) -> dict:
        if self.metrics:
            return json.loads(self.metrics)
        return {}

    def get_progress(self) -> dict:
        """Parsing progress_message menjadi dict {progress, message}."""
        if self.progress_message:
            try:
                return json.loads(self.progress_message)
            except:
                pass
        return {"progress": 0, "message": ""}

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "model_id": self.model_id,
            "data_size": self.data_size,
            "duration": self.duration,
            "status": self.status,
            "error_message": self.error_message,
            "metrics": self.get_metrics(),
            "progress": self.get_progress(),
            "dataset_filename": self.dataset_filename,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "task_id": self.task_id,
        }