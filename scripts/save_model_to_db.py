"""
scripts/save_model_to_db.py
───────────────────────────
Simpan artifact ClassifierChain ke database sebagai dua model (stress & motivasi).
"""

import os, sys, joblib
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app, db
from app.models import MLModel


def save_model_to_db(
    model_type: str,
    file_path: str,
    algorithm: str,
    version: str,
    accuracy: float,
    precision_score: float,
    recall_score: float,
    f1_score: float,
    data_count: int,
    is_active: bool = True,
):
    app = create_app()
    with app.app_context():
        if not os.path.exists(file_path):
            print(f"❌ File tidak ditemukan: {file_path}")
            return False

        artifact = joblib.load(file_path)
        # Konversi numpy jika ada
        for key in ['bins_stress', 'bins_motivasi']:
            if key in artifact and isinstance(artifact[key], list):
                # Biarkan, hanya untuk metadata
                pass

        # Metadata artifact
        artifact_metadata = {
            'bins_stress': artifact.get('bins_stress', {}),
            'bins_motivasi': artifact.get('bins_motivasi', {}),
            'demo_categories': artifact.get('demo_categories', {}),
            'best_params': artifact.get('best_params', {}),
            'cv_macro_f1': artifact.get('cv_macro_f1', None),
            'chain_order': artifact.get('params', {}).get('chain_order', [1, 0]),
        }

        existing = MLModel.query.filter_by(type=model_type).first()
        if existing:
            print(f"[*] Update existing {model_type}...")
            existing.algorithm = algorithm
            existing.version = version
            existing.accuracy = accuracy
            existing.precision_score = precision_score
            existing.recall_score = recall_score
            existing.f1_score = f1_score
            existing.file_path = file_path
            existing.is_active = is_active
            existing.data_count = data_count
            existing.set_artifact_metadata(artifact_metadata)
        else:
            print(f"[*] Create new {model_type}...")
            new_model = MLModel(
                type=model_type,
                algorithm=algorithm,
                version=version,
                accuracy=accuracy,
                precision_score=precision_score,
                recall_score=recall_score,
                f1_score=f1_score,
                file_path=file_path,
                is_active=is_active,
                data_count=data_count,
            )
            new_model.set_artifact_metadata(artifact_metadata)
            db.session.add(new_model)
        db.session.commit()
        print(f"✅ {model_type} saved")
        return True


def main():
    print("=" * 70)
    print("SAVE CLASSIFIER CHAIN MODEL TO DB")
    print("=" * 70)

    artifact_path = 'storage/models/model_chain_final.joblib'
    if not os.path.exists(artifact_path):
        print(f"❌ Artifact tidak ditemukan: {artifact_path}")
        return

    print(f"✅ Artifact ditemukan: {artifact_path}")

    # Simpan model STRESS (kolom 0)
    save_model_to_db(
        model_type='stress',
        file_path=artifact_path,
        algorithm='ClassifierChain_RF',
        version='v2.0',
        accuracy=0.93,          # Akurasi stress dari evaluasi
        precision_score=0.94,
        recall_score=0.93,
        f1_score=0.93,
        data_count=180,
        is_active=True,
    )

    # Simpan model MOTIVASI (kolom 1)
    save_model_to_db(
        model_type='motivasi',
        file_path=artifact_path,
        algorithm='ClassifierChain_RF',
        version='v2.0',
        accuracy=0.88,          # Akurasi motivasi
        precision_score=0.89,
        recall_score=0.87,
        f1_score=0.88,
        data_count=180,
        is_active=True,
    )

    print("\n✅ SEMUA MODEL BERHASIL DISIMPAN")


if __name__ == '__main__':
    main()