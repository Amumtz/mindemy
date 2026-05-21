"""
scripts/update_model_chain.py
──────────────────────────────
Update record model stress & motivasi ke ClassifierChain,
membaca metadata dari artifact langsung.
"""

import os, sys, joblib, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db
from app.models import MLModel

ARTIFACT_PATH = 'storage/models/model_chain_final.joblib'

def update_model(record_id, metrics):
    app = create_app()
    with app.app_context():
        model = MLModel.query.get(record_id)
        if not model:
            print(f"❌ Model id={record_id} tidak ditemukan")
            return

        # Update metric & info
        model.algorithm = 'ClassifierChain_RF'
        model.version = 'v2.0'
        model.accuracy = metrics['accuracy']
        model.precision_score = metrics['precision']
        model.recall_score = metrics['recall']
        model.f1_score = metrics['f1']
        model.data_count = metrics.get('data_count', model.data_count)
        model.file_path = ARTIFACT_PATH
        model.qcut_thresholds = None   # tidak dipakai lagi

        # Baca metadata dari artifact
        artifact = joblib.load(ARTIFACT_PATH)

        # Konversi numpy array menjadi list (jika ada)
        bins_stress = artifact.get('bins_stress', {})
        if hasattr(bins_stress, 'tolist'):
            bins_stress = bins_stress.tolist()
        bins_motivasi = artifact.get('bins_motivasi', {})
        if hasattr(bins_motivasi, 'tolist'):
            bins_motivasi = bins_motivasi.tolist()

        artifact_metadata = {
            'bins_stress': bins_stress,
            'bins_motivasi': bins_motivasi,
            'demo_categories': artifact.get('demo_categories', {}),
            'best_params': artifact.get('best_params', artifact.get('params', {})),
            'cv_macro_f1': artifact.get('cv_macro_f1', None),
            'chain_order': [1, 0],  # sesuai artifact
        }
        model.set_artifact_metadata(artifact_metadata)

        db.session.commit()
        print(f"✅ Model id={record_id} ({model.type}) diupdate.")
        print(f"   accuracy={model.accuracy}, f1={model.f1_score}")


if __name__ == '__main__':
    # Metrics dari classification report (weighted avg)
    stress_metrics = {
        'accuracy': 0.9444,
        'precision': 0.95,
        'recall': 0.94,
        'f1': 0.95,
        'data_count': 180,
    }
    motivasi_metrics = {
        'accuracy': 0.8889,
        'precision': 0.90,
        'recall': 0.89,
        'f1': 0.89,
        'data_count': 180,
    }

    update_model(1, stress_metrics)    # stress
    update_model(2, motivasi_metrics)  # motivasi

    print("\n🚀 Selesai. Restart backend Flask agar model baru di-load.")