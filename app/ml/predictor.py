"""
app/ml/predictor.py
───────────────────
Singleton registry untuk model aktif (stress & motivasi).
Menyediakan prediksi dengan pipeline, bins, dan demo_categories.

Versi final – siap production setelah komentar debug dihapus.
"""

import os
import joblib
import logging
import numpy as np
import pandas as pd
import traceback
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────────
# Fungsi bantu
# ──────────────────────────────────────────────────────────────────
def _safe_get(d: dict, *keys, default=0):
    """Coba semua variasi kunci (case-insensitive)."""
    for k in keys:
        for candidate in [k, k.lower(), k.upper(), k.capitalize()]:
            if candidate in d:
                return d[candidate]
    return default


def _discretize_feature(value: float, bins: List[float]) -> int:
    """
    Konversi nilai numerik menjadi kategori diskrit menggunakan bins.
    Bins bisa berupa list atau numpy array.
    """
    try:
        bins_array = np.asarray(bins)
        value_float = float(value)
        return int(np.digitize(value_float, bins_array) - 1)
    except Exception as e:
        logger.warning(f"Error discretizing {value} dengan bins: {e}")
        return 0


# ──────────────────────────────────────────────────────────────────
# Audit (hanya untuk debugging)
# ──────────────────────────────────────────────────────────────────
def audit_input(model_type: str, input_data: Dict[str, Any]):
    """
    Cetak audit lengkap: raw input → preprocessed values.
    NONAKTIFKAN di production.
    """
    bundle = registry._bundles.get(model_type)
    if bundle is None:
        print(f"[AUDIT] Bundle {model_type} tidak tersedia")
        return

    feature_names = bundle['feature_names']
    demo_categories = bundle.get('demo_categories', {})
    bins_stress = bundle.get('bins_stress', {})
    bins_motivasi = bundle.get('bins_motivasi', {})

    print(f"\n{'='*60}")
    print(f"[AUDIT] Input untuk model: {model_type}")
    print(f"{'='*60}")

    print("\n[1] KEY CHECK:")
    for feat in feature_names:
        present = feat in input_data
        val = input_data.get(feat, "MISSING")
        status = "✅" if present else "❌ MISSING → default 0"
        print(f"  {feat:20s} = {str(val):20s} {status}")

    print("\n[2] PREPROCESSING:")
    bins = bins_stress if model_type == "stress" else bins_motivasi
    for feat in feature_names:
        val = input_data.get(feat, 0)
        if feat in demo_categories:
            print(f"  {feat:20s} = '{val}' (categorical)")
        elif feat in bins:
            discretized = _discretize_feature(val, bins[feat])
            print(f"  {feat:20s} = {val} → bin {discretized}")
        else:
            print(f"  {feat:20s} = {val} (numeric)")
    print(f"{'='*60}\n")


# ──────────────────────────────────────────────────────────────────
# Model Registry
# ──────────────────────────────────────────────────────────────────
class ModelRegistry:
    def __init__(self):
        self._bundles: Dict[str, Dict[str, Any]] = {}
        self._metadata: Dict[str, Dict] = {}

    # ── Load ──────────────────────────────────────────────────────
    def load(self, model_type: str, file_path: str, meta: dict):
        """Muat artifact bundle dari file .joblib."""
        try:
            logger.debug("Memuat %s dari %s", model_type, file_path)
            bundle_data = joblib.load(file_path)

            # Konversi numpy → list jika perlu
            if 'bins_stress' in bundle_data and isinstance(bundle_data['bins_stress'], np.ndarray):
                bundle_data['bins_stress'] = bundle_data['bins_stress'].tolist()
            if 'bins_motivasi' in bundle_data and isinstance(bundle_data['bins_motivasi'], np.ndarray):
                bundle_data['bins_motivasi'] = bundle_data['bins_motivasi'].tolist()

            if 'demo_categories' in bundle_data:
                if isinstance(bundle_data['demo_categories'], np.ndarray):
                    bundle_data['demo_categories'] = bundle_data['demo_categories'].tolist()
                elif isinstance(bundle_data['demo_categories'], dict):
                    for k, v in bundle_data['demo_categories'].items():
                        if isinstance(v, np.ndarray):
                            bundle_data['demo_categories'][k] = v.tolist()

            if not isinstance(bundle_data, dict):
                raise ValueError(f"Bundle {model_type} harus berupa dictionary")

            for field in ['pipeline', 'feature_names', 'label_map']:
                if field not in bundle_data:
                    raise ValueError(f"Bundle {model_type} tidak memiliki '{field}'")

            pipeline = bundle_data['pipeline']
            feature_names = bundle_data['feature_names']
            label_map = bundle_data['label_map']

            bins_stress = bundle_data.get('bins_stress', {})
            bins_motivasi = bundle_data.get('bins_motivasi', {})
            
            demo_categories = bundle_data.get('demo_categories', {})
            best_params = bundle_data.get('best_params', {})
            cv_macro_f1 = bundle_data.get('cv_macro_f1', None)

            # Info ringkas
            logger.debug("Bundle %s: pipeline=%s, fitur=%d, label=%s, bins_stress=%d, bins_motivasi=%d, F1=%.4f",
                         model_type, type(pipeline).__name__, len(feature_names), label_map,
                         len(bins_stress), len(bins_motivasi),
                         cv_macro_f1 if cv_macro_f1 is not None else 0.0)

            bundle = {
                'pipeline': pipeline,
                'feature_names': feature_names,
                'label_map': label_map,
                'bins_stress': bins_stress,
                'bins_motivasi': bins_motivasi,
                'demo_categories': demo_categories,
                'best_params': best_params,
                'cv_macro_f1': cv_macro_f1,
                'model_type': model_type,
            }
            self._bundles[model_type] = bundle
            self._metadata[model_type] = meta
            logger.info("Bundle %s berhasil dimuat.", model_type)

        except Exception as exc:
            logger.error("[Registry] Gagal memuat %s: %s", model_type, exc)
            raise

    def reload_from_db(self, app):
        """Muat ulang model aktif dari database."""
        with app.app_context():
            from app.models import MLModel
            active_models = MLModel.query.filter_by(is_active=True).all()
            for row in active_models:
                if os.path.exists(row.file_path):
                    self.load(row.type, row.file_path, row.to_dict())
                else:
                    logger.warning("File model tidak ditemukan: %s", row.file_path)

    # ── Akses metadata ────────────────────────────────────────────
    def is_loaded(self, model_type: str) -> bool:
        return model_type in self._bundles

    def get_metadata(self, model_type: str) -> Dict:
        return self._metadata.get(model_type, {})

    def get_feature_names(self, model_type: str) -> List[str]:
        return self._bundles.get(model_type, {}).get('feature_names', [])

    def get_label_map(self, model_type: str) -> Dict[int, str]:
        return self._bundles.get(model_type, {}).get('label_map', {})

    # ── Prediksi ──────────────────────────────────────────────────
    def predict(self, model_type: str, input_data: Dict[str, Any]) -> Optional[str]:
        """Jalankan prediksi untuk model 'stress' atau 'motivasi'."""
        bundle = self._bundles.get(model_type)
        if bundle is None:
            logger.warning("Bundle untuk %s tidak tersedia", model_type)
            return None

        try:
            X = self._prepare_input_dataframe(bundle, input_data)
            pipeline = bundle['pipeline']

            # Prediksi MultiOutput → shape (n_samples, 2)
            preds = pipeline.predict(X)
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

    # ── Persiapan DataFrame input ─────────────────────────────────
    def _prepare_input_dataframe(self, bundle: Dict, input_data: Dict) -> pd.DataFrame:
        """Buat DataFrame 1-baris sesuai format yang diharapkan pipeline."""
        feature_names = bundle['feature_names']
        demo_categories = bundle.get('demo_categories', {})
        bins_stress = bundle.get('bins_stress', {})
        bins_motivasi = bundle.get('bins_motivasi', {})
        model_type = bundle['model_type']

        bins = bins_stress if model_type == "stress" else bins_motivasi

        # Validasi format bins
        if isinstance(bins, (list, np.ndarray)):
            logger.warning("[%s] bins list/array, diskritisasi dinonaktifkan.", model_type)
            bins = {}
        elif not isinstance(bins, dict):
            logger.warning("[%s] bins tipe %s tidak valid.", model_type, type(bins))
            bins = {}

        row_data = {}
        for feat in feature_names:
            val = input_data.get(feat, 0)

            # Kolom kategorikal → sesuaikan tipe dengan data training
            if isinstance(demo_categories, dict) and feat in demo_categories:
                cats = demo_categories[feat]
                if len(cats) > 0:
                    sample_cat = cats[0]
                    if isinstance(sample_cat, str):
                        row_data[feat] = str(val)
                    elif isinstance(sample_cat, (int, np.integer)):
                        try:
                            row_data[feat] = int(float(val))
                        except (ValueError, TypeError):
                            row_data[feat] = 0
                    elif isinstance(sample_cat, (float, np.floating)):
                        try:
                            row_data[feat] = float(val)
                        except (ValueError, TypeError):
                            row_data[feat] = 0.0
                    else:
                        row_data[feat] = str(val)
                else:
                    row_data[feat] = str(val)

            # Kolom numerik dengan bins
            elif isinstance(bins, dict) and feat in bins:
                row_data[feat] = _discretize_feature(val, bins[feat])

            # Kolom numerik lainnya
            else:
                try:
                    row_data[feat] = float(val)
                except (ValueError, TypeError):
                    row_data[feat] = 0.0

        return pd.DataFrame([row_data], columns=feature_names)


# ──────────────────────────────────────────────────────────────────
# Singleton
# ──────────────────────────────────────────────────────────────────
registry = ModelRegistry()


# ──────────────────────────────────────────────────────────────────
# Fungsi bantu eksternal
# ──────────────────────────────────────────────────────────────────
def get_demo_categories(model_type: str) -> Dict[str, List[str]]:
    bundle = registry._bundles.get(model_type)
    if not bundle:
        return {}
    demo_cat = bundle.get('demo_categories', {})
    return demo_cat if isinstance(demo_cat, dict) else {}


def get_bins(model_type: str) -> Any:  # bisa mengembalikan list atau dict
    bundle = registry._bundles.get(model_type)
    if not bundle:
        return {} if model_type != 'stress' else {}
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
    input_dict = {
        "IPK":    _safe_get(mahasiswa_data, "IPK", "ipk", default=0.0),
        "Usia":   _safe_get(mahasiswa_data, "Usia", "usia", default=20),
        "Jurusan": _safe_get(mahasiswa_data, "nama_jurusan", "jurusan", "Jurusan", default=""),
        "Gender": _safe_get(mahasiswa_data, "Gender", "gender", default=""),
        "freq_olahraga": _safe_get(mahasiswa_data, "freq_olahraga", "FreqOlahraga", default=""),
        "durasi_tidur":  _safe_get(mahasiswa_data, "durasi_tidur",  "DurasiTidur",  default=""),
        "Angkatan": _safe_get(mahasiswa_data, "Angkatan", "angkatan", default=2023),
    }
    for i in range(1, 29):
        input_dict[f"M{i}"] = jawaban_kuesioner.get(f"M{i}", 0)
    for i in range(1, 41):
        input_dict[f"S{i}"] = jawaban_kuesioner.get(f"S{i}", 0)
    return input_dict