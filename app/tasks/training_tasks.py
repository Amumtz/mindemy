"""
app/tasks/training_tasks.py
───────────────────────────
Celery instance factory dan task training model asinkron.
Diperbarui: mendukung progress tracking via DB untuk dashboard admin,
serta status 'queued','running','completed','failed'.
"""

import os
import json
import logging
from celery import Celery

logger = logging.getLogger(__name__)


def make_celery(app):
    """
    Membuat instance Celery yang terikat dengan Flask app.
    """
    celery = Celery(
        app.import_name,
        broker=app.config["CELERY_BROKER_URL"],
        backend=app.config["CELERY_RESULT_BACKEND"],
    )
    celery.conf.update(app.config)

    class ContextTask(celery.Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return super().__call__(*args, **kwargs)

    celery.Task = ContextTask
    return celery


def register_train_task(celery_app, flask_app):
    """
    Mendaftarkan task training ke instance Celery dan menyimpan referensinya
    di flask_app.extensions sehingga bisa diakses dari blueprint.
    """

    @celery_app.task(bind=True, name="tasks.train_model")
    def train_model_task(self, history_id: int, csv_path: str,
                         model_type: str, algorithm: str,
                         version: str, models_folder: str):
        """
        Task Celery untuk menjalankan training model asinkron.

        Parameter:
        - history_id: ID baris di tabel TrainingHistory untuk tracking.
        - csv_path: Path absolut file dataset CSV.
        - model_type: 'stress' atau 'motivasi'.
        - algorithm: Algoritma yang digunakan.
        - version: Versi model (string, misal 'stress_v2').
        - models_folder: Folder penyimpanan file model (.joblib).

        Task ini akan memperbarui baris TrainingHistory secara langsung
        dengan status dan progress, sehingga frontend dapat melakukan polling.
        """
        from app.extensions import db
        from app.models import TrainingHistory, MLModel
        from app.ml.trainer import train_model

        history = TrainingHistory.query.get(history_id)
        if not history:
            logger.error(f"TrainingHistory dengan id {history_id} tidak ditemukan.")
            return {"error": "history not found"}

        # Helper untuk memperbarui progress ke database
        def update_progress_db(pct: int, message: str):
            try:
                history.progress_message = json.dumps({
                    "progress": pct,
                    "message": message
                })
                db.session.commit()
                # Opsional: update state Celery untuk monitoring (Flower, dll.)
                self.update_state(state="PROGRESS", meta={"pct": pct, "message": message})
            except Exception as e:
                logger.error(f"Gagal update progress: {e}")

        try:
            # 1. Tandai sebagai running dan progress awal
            history.status = 'running'
            update_progress_db(0, "Memulai training...")
            db.session.commit()

            # 2. Jalankan pelatihan dengan callback progress
            # Pastikan fungsi train_model di app/ml/trainer.py menerima parameter
            # `progress_callback` dan memanggilnya seperti:
            #   if progress_callback:
            #       progress_callback(30, "Melatih model...")
            result = train_model(
                csv_path=csv_path,
                model_type=model_type,
                algorithm=algorithm,
                models_folder=models_folder,
                version=version,
                progress_callback=update_progress_db
            )

            # 3. Update progress sebelum menyimpan ke database
            update_progress_db(90, "Menyimpan model ke database...")

            # 4. Nonaktifkan semua model aktif dengan tipe yang sama
            MLModel.query.filter_by(type=model_type, is_active=True).update(
                {"is_active": False}
            )

            # 5. Buat record model baru
            new_model = MLModel(
                type=model_type,
                algorithm=algorithm,
                version=version,
                accuracy=result["accuracy"],
                precision_score=result["precision_score"],
                recall_score=result["recall_score"],
                f1_score=result["f1_score"],
                file_path=result["file_path"],
                is_active=True,
                data_count=result["data_count"],
                qcut_thresholds=json.dumps(result["thresholds"]),
                artifact_metadata=json.dumps(result.get("artifact_metadata", {}))
            )
            db.session.add(new_model)
            db.session.flush()  # Mendapatkan new_model.id

            # 6. Perbarui history menjadi completed
            history.status = 'completed'
            history.model_id = new_model.id
            history.duration = result["duration"]
            history.metrics = json.dumps(result["metrics"])
            history.data_size = result["data_count"]
            history.progress_message = json.dumps({"progress": 100, "message": "Selesai"})
            db.session.commit()

            # 7. Muat ulang model ke registry in-memory agar API prediksi langsung pakai model baru
            from app.ml.predictor import registry
            registry.load(
                model_type,
                result["file_path"],
                new_model.to_dict() | {"thresholds": result["thresholds"]}
            )

            logger.info(f"[Task] Training selesai: model_id={new_model.id}")
            return {
                "status": "completed",
                "model_id": new_model.id,
                **result["metrics"]
            }

        except Exception as exc:
            # 8. Tangani error: tandai failed, simpan pesan error
            logger.error(f"[Task] Training gagal: {exc}", exc_info=True)
            history.status = 'failed'
            history.error_message = str(exc)
            history.progress_message = json.dumps({
                "progress": 0,
                "message": f"Error: {str(exc)}"
            })
            db.session.commit()
            self.update_state(state="FAILURE", meta={"error": str(exc)})
            raise

    # Simpan referensi task agar bisa diakses dari blueprint admin
    flask_app.extensions["celery_train_task"] = train_model_task
    return train_model_task