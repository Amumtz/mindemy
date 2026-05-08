"""
scripts/save_model_to_db.py
───────────────────────────
Script untuk menyimpan artifact model dari file ke database.

Usage:
    python save_model_to_db.py

Requirement:
    - File artifact sudah ada: storage/models/model_v1.joblib
    - Artifact harus memiliki struktur:
      {
        'pipeline': Pipeline,
        'feature_names': List[str],
        'label_map': Dict[int, str],
        'bins_stress': Dict[str, List[float]],
        'bins_motivasi': Dict[str, List[float]],
        'demo_categories': Dict[str, List[str]],
        'best_params': Dict,
        'cv_macro_f1': float
      }
"""

import os
import sys
import joblib
import json

# Add parent directory ke path
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
    """
    Load artifact dari file dan simpan metadata ke database.
    
    Args:
        model_type: 'stress' atau 'motivasi'
        file_path: Path ke artifact file (misal: storage/models/model_v1.joblib)
        algorithm: Nama algorithm (misal: RandomForest_BR_balanced)
        version: Versi model (misal: v1.0)
        accuracy, precision_score, recall_score, f1_score: Metrics
        data_count: Jumlah data training
        is_active: Apakah model aktif untuk prediksi
    """
    app = create_app()
    
    with app.app_context():
        # Validasi file
        if not os.path.exists(file_path):
            print(f"❌ File tidak ditemukan: {file_path}")
            return False
        
        # Load artifact
        print(f"[*] Loading artifact dari {file_path}...")
        try:
            artifact = joblib.load(file_path)
        except Exception as e:
            print(f"❌ Gagal load artifact: {e}")
            return False
        
        # Validasi struktur artifact
        required_fields = ['pipeline', 'feature_names', 'label_map']
        for field in required_fields:
            if field not in artifact:
                print(f"❌ Artifact tidak memiliki field wajib: '{field}'")
                return False
        
        # Extract metadata dari artifact
        bins_stress = artifact.get('bins_stress', {})
        bins_motivasi = artifact.get('bins_motivasi', {})
        demo_categories = artifact.get('demo_categories', {})
        best_params = artifact.get('best_params', {})
        cv_macro_f1 = artifact.get('cv_macro_f1', None)
        
        print(f"[*] Artifact metadata:")
        print(f"    - bins_stress: {type(bins_stress).__name__} dengan {len(bins_stress)} features")
        print(f"    - bins_motivasi: {type(bins_motivasi).__name__} dengan {len(bins_motivasi)} features")
        print(f"    - demo_categories: {type(demo_categories).__name__} dengan {len(demo_categories)} features")
        print(f"    - best_params: {len(best_params)} params")
        print(f"    - cv_macro_f1: {cv_macro_f1}")
        
        artifact_metadata = {
            'bins_stress': bins_stress,
            'bins_motivasi': bins_motivasi,
            'demo_categories': demo_categories,
            'best_params': best_params,
            'cv_macro_f1': cv_macro_f1,
        }
        
        # Cek apakah model dengan type yang sama sudah ada
        existing_model = MLModel.query.filter_by(type=model_type).first()
        
        if existing_model:
            print(f"[*] Model {model_type} sudah ada di database (ID: {existing_model.id})")
            print(f"[*] Mengupdate dengan artifact baru...")
            
            try:
                # Update existing model
                existing_model.algorithm = algorithm
                existing_model.version = version
                existing_model.accuracy = accuracy
                existing_model.precision_score = precision_score
                existing_model.recall_score = recall_score
                existing_model.f1_score = f1_score
                existing_model.file_path = file_path
                existing_model.is_active = is_active
                existing_model.data_count = data_count
                existing_model.set_artifact_metadata(artifact_metadata)
                
                db.session.commit()
                print(f"✅ Model {model_type} berhasil diupdate")
                return True
            except Exception as e:
                print(f"❌ Error saat update model: {e}")
                db.session.rollback()
                return False
        
        else:
            print(f"[*] Membuat model {model_type} baru di database...")
            
            try:
                # Create new model
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
                print(f"✅ Model {model_type} berhasil dibuat (ID: {new_model.id})")
                return True
            except Exception as e:
                print(f"❌ Error saat create model: {e}")
                db.session.rollback()
                return False


def main():
    """Main entry point."""
    print("=" * 70)
    print("SAVE MODEL TO DATABASE")
    print("=" * 70)
    
    # Validasi file artifact
    artifact_path = 'storage/models/model_v1.joblib'
    if not os.path.exists(artifact_path):
        print(f"❌ File artifact tidak ditemukan: {artifact_path}")
        print(f"   Path absolute: {os.path.abspath(artifact_path)}")
        return
    
    print(f"\n✅ File artifact ditemukan: {artifact_path}")
    print(f"   Size: {os.path.getsize(artifact_path) / 1024 / 1024:.2f} MB")
    
    # Konfigurasi model stress
    print("\n[1/2] Menyimpan model STRESS...")
    success_stress = save_model_to_db(
        model_type='stress',
        file_path=artifact_path,
        algorithm='RandomForest_BR_balanced',
        version='v1.0',
        accuracy=0.94,
        precision_score=0.95,
        recall_score=0.95,
        f1_score=0.94,
        data_count=150,  # Sesuaikan dengan jumlah data training Anda
        is_active=True,
    )
    
    # Konfigurasi model motivasi
    print("\n[2/2] Menyimpan model MOTIVASI...")
    success_motivasi = save_model_to_db(
        model_type='motivasi',
        file_path=artifact_path,
        algorithm='RandomForest_BR_balanced',
        version='v1.0',
        accuracy=0.75,
        precision_score=0.78,
        recall_score=0.75,
        f1_score=0.76,
        data_count=150,  # Sesuaikan dengan jumlah data training Anda
        is_active=True,
    )
    
    print("\n" + "=" * 70)
    if success_stress and success_motivasi:
        print("✅ SEMUA MODEL BERHASIL DISIMPAN")
    else:
        print("⚠️  BEBERAPA MODEL GAGAL DISIMPAN")
    print("=" * 70)


if __name__ == '__main__':
    main()
