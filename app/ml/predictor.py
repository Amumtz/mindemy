"""
app/ml/predictor.py
───────────────────
Singleton registry untuk model ClassifierChain (stres & motivasi dalam satu pipeline).
"""

import os
import joblib
import logging
import numpy as np
import pandas as pd
import traceback
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)


def _safe_get(d: dict, *keys, default=0):
    for k in keys:
        for candidate in [k, k.lower(), k.upper(), k.capitalize()]:
            if candidate in d:
                return d[candidate]
    return default


# ────────────────────────── Registry ──────────────────────────────
class ModelRegistry:
    def __init__(self):
        self._bundles: Dict[str, Dict[str, Any]] = {}
        self._metadata: Dict[str, Dict] = {}

    def load(self, model_type: str, file_path: str, meta: dict):
        """Muat artifact bundle (satu file untuk kedua tipe)."""
        try:
            # Jika sudah pernah dimuat dengan file yang sama, gunakan cache
            existing = self._find_bundle_by_path(file_path)
            if existing:
                logger.info("Bundle dari %s sudah dimuat, pakai ulang", file_path)
                self._bundles[model_type] = existing
                self._metadata[model_type] = meta
                return

            logger.debug("Memuat %s dari %s", model_type, file_path)
            bundle_data = joblib.load(file_path)

            # Konversi numpy → list untuk JSON serialization
            bundle_data = self._convert_numpy(bundle_data)

            if not isinstance(bundle_data, dict):
                raise ValueError(f"Bundle {model_type} harus dictionary")

            required = ['pipeline', 'feature_names', 'label_map']
            for field in required:
                if field not in bundle_data:
                    raise ValueError(f"Bundle {model_type} tidak memiliki '{field}'")

            bundle = {
                'pipeline': bundle_data['pipeline'],
                'feature_names': bundle_data['feature_names'],
                'label_map': bundle_data['label_map'],
                'demo_categories': bundle_data.get('demo_categories', {}),
                'bins_stress': bundle_data.get('bins_stress', {}),
                'bins_motivasi': bundle_data.get('bins_motivasi', {}),
                'best_params': bundle_data.get('best_params', {}),
                'cv_macro_f1': bundle_data.get('cv_macro_f1', None),
                'model_type': model_type,
            }
            self._bundles[model_type] = bundle
            self._metadata[model_type] = meta
            logger.info("Bundle %s berhasil dimuat.", model_type)

        except Exception as exc:
            logger.error("[Registry] Gagal memuat %s: %s", model_type, exc)
            raise

    def _find_bundle_by_path(self, path: str):
        """Cek apakah path sudah dimuat di salah satu bundle."""
        for bundle in self._bundles.values():
            if bundle.get('_file_path') == path:
                return bundle
        return None

    def _convert_numpy(self, obj):
        """Konversi numpy array di dalam dict ke list (rekursif)."""
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, dict):
            return {k: self._convert_numpy(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._convert_numpy(v) for v in obj]
        return obj

    def reload_from_db(self, app):
        with app.app_context():
            from app.models import MLModel
            active_models = MLModel.query.filter_by(is_active=True).all()
            for row in active_models:
                if os.path.exists(row.file_path):
                    self.load(row.type, row.file_path, row.to_dict())
                else:
                    logger.warning("File model tidak ditemukan: %s", row.file_path)

    def is_loaded(self, model_type: str) -> bool:
        return model_type in self._bundles

    def get_metadata(self, model_type: str) -> Dict:
        return self._metadata.get(model_type, {})

    def get_feature_names(self, model_type: str) -> List[str]:
        return self._bundles.get(model_type, {}).get('feature_names', [])

    def get_label_map(self, model_type: str) -> Dict[int, str]:
        return self._bundles.get(model_type, {}).get('label_map', {})

    # ── Prediksi ClassifierChain ─────────────────────────────────
    def predict(self, model_type: str, input_data: Dict[str, Any]) -> Optional[str]:
        bundle = self._bundles.get(model_type)
        if bundle is None:
            logger.warning("Bundle untuk %s tidak tersedia", model_type)
            return None

        try:
            X = self._prepare_input_dataframe(bundle, input_data)
            pipeline = bundle['pipeline']

            # Prediksi MultiOutput → shape (n_samples, 2)
            preds = pipeline.predict(X)
            # Kolom: 0 = stress, 1 = motivasi
            target_idx = 0 if model_type == 'stress' else 1
            pred_numeric = int(preds[0, target_idx])

            label_map = bundle['label_map']
            result = label_map.get(pred_numeric, "Tidak Diketahui")
            logger.debug("[%s] prediksi=%d → %s", model_type, pred_numeric, result)
            return result

        except Exception as exc:
            logger.error("[Registry] Error prediksi %s: %s", model_type, exc)
            traceback.print_exc()
            return None

    def _prepare_input_dataframe(self, bundle: Dict, input_data: Dict) -> pd.DataFrame:
        """
        Buat DataFrame 1-baris untuk pipeline ClassifierChain.
        Tidak melakukan diskritisasi manual karena preprocessor di dalam pipeline menangani.
        """
        feature_names = bundle['feature_names']
        row_data = {}

        for feat in feature_names:
            val = input_data.get(feat, 0)

            # Deteksi tipe dari demo_categories
            demo_categories = bundle.get('demo_categories', {})
            if feat in demo_categories:
                # Kategorikal → string
                row_data[feat] = str(val)
            else:
                # Numerik → float
                try:
                    row_data[feat] = float(val)
                except (ValueError, TypeError):
                    row_data[feat] = 0.0

        return pd.DataFrame([row_data], columns=feature_names)


# ── Singleton ─────────────────────────────────────────────────────
registry = ModelRegistry()


# ── Fungsi helper ─────────────────────────────────────────────────
def get_demo_categories(model_type: str) -> Dict[str, List[str]]:
    bundle = registry._bundles.get(model_type)
    if not bundle:
        return {}
    demo_cat = bundle.get('demo_categories', {})
    return demo_cat if isinstance(demo_cat, dict) else {}


def get_bins(model_type: str) -> Any:
    bundle = registry._bundles.get(model_type)
    if not bundle:
        return {}
    key = 'bins_stress' if model_type == 'stress' else 'bins_motivasi'
    return bundle.get(key, {})


def prepare_stress_input(mahasiswa_data: Dict, jawaban_kuesioner: Dict) -> Dict[str, Any]:
    input_dict = {
        "IPK":    _safe_get(mahasiswa_data, "IPK", "ipk", default=0.0),
        "Usia":   _safe_get(mahasiswa_data, "Usia", "usia", default=20),
        "Jurusan": _safe_get(mahasiswa_data, "nama_jurusan", "jurusan", "Jurusan", default=""),
        "Gender": _safe_get(mahasiswa_data, "Gender", "gender", default=""),
        "freq_olahraga": _safe_get(mahasiswa_data, "freq_olahraga", "FreqOlahraga", default=""),
        "durasi_tidur":  _safe_get(mahasiswa_data, "durasi_tidur",  "DurasiTidur",  default=""),
        "Angkatan": _safe_get(mahasiswa_data, "Angkatan", "angkatan", default=2023),
    }
    for i in range(1, 41):
        input_dict[f"S{i}"] = jawaban_kuesioner.get(f"S{i}", 0)
    for i in range(1, 29):
        input_dict[f"M{i}"] = jawaban_kuesioner.get(f"M{i}", 0)
    return input_dict


def prepare_motivasi_input(mahasiswa_data: Dict, jawaban_kuesioner: Dict) -> Dict[str, Any]:
    # Sama saja, karena fitur identik untuk kedua model
    return prepare_stress_input(mahasiswa_data, jawaban_kuesioner)