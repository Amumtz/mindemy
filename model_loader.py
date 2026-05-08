"""
Model Loader - Load Model, Scaler, dan Feature Order untuk Prediksi
Gunakan file ini untuk load model terlebih dahulu sebelum prediksi
"""
import pickle
import json
import numpy as np
from pathlib import Path

class PredictionModel:
    def __init__(self, model_dir='./models'):
        """Initialize dengan load semua model, scaler, dan feature order"""
        self.model_dir = Path(model_dir)
        
        # Load models
        self.model_motivasi = self._load_file('model_motivasi_v1.pkl')
        self.model_stress = self._load_file('model_stress_v1.pkl')
        
        # Load scalers
        self.scaler_motivasi = self._load_file('scaler_motivasi_v1.pkl')
        self.scaler_stress = self._load_file('scaler_stress_v1.pkl')
        
        # Load feature orders
        self.features_motivasi = self._load_json('features_motivasi_v1.json')
        self.features_stress = self._load_json('features_stress_v1.json')
        
        print("✓ Model, Scaler, dan Feature Orders berhasil dimuat!")
        print(f"  - Motivasi: {len(self.features_motivasi)} fitur")
        print(f"  - Stress: {len(self.features_stress)} fitur")
    
    def _load_file(self, filename):
        """Load pickle file"""
        filepath = self.model_dir / filename
        with open(filepath, 'rb') as f:
            return pickle.load(f)
    
    def _load_json(self, filename):
        """Load JSON file"""
        filepath = self.model_dir / filename
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def _prepare_features(self, input_dict, feature_order):
        """Siapkan fitur sesuai urutan dan convert ke array"""
        features_list = [input_dict[feat] for feat in feature_order]
        return np.array(features_list, dtype=np.float32).reshape(1, -1)
    
    def predict_motivasi(self, input_dict):
        """
        Prediksi Motivasi
        
        Args:
            input_dict: Dictionary dengan 75 fitur
        
        Returns:
            {"prediction": int, "probabilities": list, "confidence": float}
        """
        X = self._prepare_features(input_dict, self.features_motivasi)
        X_scaled = self.scaler_motivasi.transform(X)
        
        prediction = self.model_motivasi.predict(X_scaled)[0]
        probabilities = self.model_motivasi.predict_proba(X_scaled)[0]
        confidence = float(max(probabilities))
        
        return {
            "prediction": int(prediction),
            "probabilities": [float(p) for p in probabilities],
            "confidence": confidence
        }
    
    def predict_stress(self, input_dict):
        """
        Prediksi Stress
        
        Args:
            input_dict: Dictionary dengan 75 fitur
        
        Returns:
            {"prediction": int, "probabilities": list, "confidence": float}
        """
        X = self._prepare_features(input_dict, self.features_stress)
        X_scaled = self.scaler_stress.transform(X)
        
        prediction = self.model_stress.predict(X_scaled)[0]
        probabilities = self.model_stress.predict_proba(X_scaled)[0]
        confidence = float(max(probabilities))
        
        return {
            "prediction": int(prediction),
            "probabilities": [float(p) for p in probabilities],
            "confidence": confidence
        }
    
    def predict_both(self, input_dict):
        """Prediksi kedua model sekaligus"""
        return {
            "motivasi": self.predict_motivasi(input_dict),
            "stress": self.predict_stress(input_dict)
        }


# ============================================================================
# TEST & USAGE EXAMPLE
# ============================================================================

if __name__ == "__main__":
    # Load model
    model = PredictionModel(model_dir='./models')
    
    # Buat dummy data dengan 75 fitur
    dummy_features = {
        "IPK": 3.5,
        **{f"M{i}": (i % 4) + 1 for i in range(1, 29)},  # M1-M28
        **{f"S{i}": (i % 4) + 1 for i in range(1, 41)},  # S1-S40
        "freq_olahraga": 3,
        "durasi_tidur": 8,
        "Usia": 20,
        "Jurusan": 1,
        "Gender": 1,
        "Angkatan": 2021
    }
    
    print(f"\n📊 Total fitur: {len(dummy_features)}")
    
    # Prediksi
    print("\n🔮 Prediksi Motivasi:")
    result_motivasi = model.predict_motivasi(dummy_features)
    print(f"  Prediction: {result_motivasi['prediction']}")
    print(f"  Confidence: {result_motivasi['confidence']:.4f}")
    
    print("\n🔮 Prediksi Stress:")
    result_stress = model.predict_stress(dummy_features)
    print(f"  Prediction: {result_stress['prediction']}")
    print(f"  Confidence: {result_stress['confidence']:.4f}")
    
    print("\n✅ Siap digunakan!")
