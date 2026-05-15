import os
import json
import joblib
import numpy as np
import pandas as pd
from datetime import datetime
from flask import current_app

from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder, StandardScaler, OrdinalEncoder
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.ensemble import RandomForestClassifier
from sklearn.multioutput import MultiOutputClassifier
from sklearn.metrics import accuracy_score, classification_report

from app.extensions import db
from app.models import MLModel, TrainingHistory

FITUR_STRESS = [f"S{i}" for i in range(1, 41)]
FITUR_MOTIVASI = [f"M{i}" for i in range(1, 29)]
FITUR_DEMO = ['Jurusan', 'Angkatan', 'Gender', 'Usia', 'IPK',
              'freq_olahraga', 'durasi_tidur']

def train_model(history_id, csv_path, model_type, hyperparams=None, models_folder="models"):
    history = TrainingHistory.query.get(history_id)
    if not history:
        return

    try:
        # Update status
        history.status = "running"
        history.progress_message = json.dumps({"progress": 10, "message": "Membaca dataset..."})
        db.session.commit()

        # Baca file
        df = pd.read_csv(csv_path) if csv_path.endswith('.csv') else pd.read_excel(csv_path)

        # ── 1. Buat label stress ──────────────────────────────────
        stress_cols = [f"S{i}" for i in range(1, 41)]
        df['total_stress'] = df[stress_cols].sum(axis=1)
        df['label_stress'], bins_stress = pd.qcut(
            df['total_stress'], q=3,
            labels=["Rendah", "Sedang", "Tinggi"],
            retbins=True
        )

        # ── 2. Hitung SDI & buat label motivasi ──────────────────
        # Rata‑rata subskala (masing‑masing 4 item)
        df['mean_im_know'] = df[['M1', 'M2', 'M3', 'M4']].mean(axis=1)
        df['mean_im_acc']  = df[['M5', 'M6', 'M7', 'M8']].mean(axis=1)
        df['mean_im_stim'] = df[['M9', 'M10', 'M11', 'M12']].mean(axis=1)
        df['mean_identified'] = df[['M13', 'M14', 'M15', 'M16']].mean(axis=1)
        df['mean_introjected'] = df[['M17', 'M18', 'M19', 'M20']].mean(axis=1)
        df['mean_external'] = df[['M21', 'M22', 'M23', 'M24']].mean(axis=1)
        df['mean_amotivation'] = df[['M25', 'M26', 'M27', 'M28']].mean(axis=1)

        df['intrinsic_total'] = (df['mean_im_know'] + df['mean_im_acc'] + df['mean_im_stim']) / 3
        df['controlled_extrinsic'] = (df['mean_introjected'] + df['mean_external']) / 2

        df['score_sdi'] = (2 * df['intrinsic_total']) + (1 * df['mean_identified']) - (1 * df['controlled_extrinsic']) - (2 * df['mean_amotivation'])

        df['label_motivasi'], bins_motivasi = pd.qcut(
            df['score_sdi'], q=3,
            labels=["Rendah", "Sedang", "Tinggi"],
            retbins=True
        )

        # ── 3. Encode label menjadi numerik ──────────────────────
        le_stress = LabelEncoder()
        le_motivasi = LabelEncoder()
        y_stress = le_stress.fit_transform(df['label_stress'])
        y_motivasi = le_motivasi.fit_transform(df['label_motivasi'])
        y = np.column_stack([y_stress, y_motivasi])

        # ── 4. Features ──────────────────────────────────────────
        X = df[FITUR_STRESS + FITUR_MOTIVASI + FITUR_DEMO].copy()

        # ── 5. Encode fitur kategorik demo ───────────────────────
        le_jurusan = LabelEncoder()
        le_gender = LabelEncoder()
        le_olahraga = LabelEncoder()
        le_tidur = LabelEncoder()

        df['Jurusan'] = le_jurusan.fit_transform(df['Jurusan'].astype(str))
        df['Gender'] = le_gender.fit_transform(df['Gender'].astype(str))
        df['freq_olahraga'] = le_olahraga.fit_transform(df['freq_olahraga'].astype(str))
        df['durasi_tidur'] = le_tidur.fit_transform(df['durasi_tidur'].astype(str))

        def ordered_cats(mapping):
            return [k for k, v in sorted(mapping.items(), key=lambda x: x[1])]

        mapping_jurusan = dict(zip(le_jurusan.classes_, range(len(le_jurusan.classes_))))
        mapping_gender = dict(zip(le_gender.classes_, range(len(le_gender.classes_))))
        mapping_olahraga = dict(zip(le_olahraga.classes_, range(len(le_olahraga.classes_))))
        mapping_tidur = dict(zip(le_tidur.classes_, range(len(le_tidur.classes_))))

        cats_jurusan = ordered_cats(mapping_jurusan)
        cats_gender = ordered_cats(mapping_gender)
        cats_olahraga = ordered_cats(mapping_olahraga)
        cats_tidur = ordered_cats(mapping_tidur)

        demo_encoder = OrdinalEncoder(
            categories=[cats_jurusan, cats_gender, cats_olahraga, cats_tidur],
            handle_unknown='use_encoded_value',
            unknown_value=-1
        )

        preprocessor = ColumnTransformer([
            ('scaler_stress', StandardScaler(), FITUR_STRESS),
            ('scaler_motivasi', StandardScaler(), FITUR_MOTIVASI),
            ('demo_encoder', demo_encoder, ['Jurusan', 'Gender', 'freq_olahraga', 'durasi_tidur'])
        ], remainder='passthrough')

        # ── 6. Split ─────────────────────────────────────────────
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42, stratify=y[:, 0]
        )

        # ── 7. Hyperparams ───────────────────────────────────────
        params = {
            'n_estimators': 100,
            'max_depth': 10,
            'min_samples_leaf': 3,
            'max_features': 'sqrt',
            'class_weight': 'balanced',
            'random_state': 42
        }
        if hyperparams and 'params' in hyperparams:
            params.update(hyperparams['params'])

        base_rf = RandomForestClassifier(**params)
        multi_rf = MultiOutputClassifier(base_rf)

        pipeline = Pipeline([
            ('preprocess', preprocessor),
            ('clf', multi_rf)
        ])

        history.progress_message = json.dumps({"progress": 50, "message": "Melatih model..."})
        db.session.commit()

        pipeline.fit(X_train, y_train)
        y_pred = pipeline.predict(X_test)

        # ── 8. Evaluasi ──────────────────────────────────────────
        acc_stress = accuracy_score(y_test[:, 0], y_pred[:, 0])
        acc_motivasi = accuracy_score(y_test[:, 1], y_pred[:, 1])
        exact_match = np.mean(np.all(y_test == y_pred, axis=1))

        report_stress = classification_report(
            y_test[:, 0], y_pred[:, 0],
            target_names=['Rendah', 'Sedang', 'Tinggi'],
            output_dict=True
        )
        report_motivasi = classification_report(
            y_test[:, 1], y_pred[:, 1],
            target_names=['Rendah', 'Sedang', 'Tinggi'],
            output_dict=True
        )

        metrics = {
            'exact_match': round(exact_match, 4),
            'accuracy_stress': round(acc_stress, 4),
            'accuracy_motivasi': round(acc_motivasi, 4),
            'report_stress': report_stress,
            'report_motivasi': report_motivasi
        }

        # ── 9. Simpan model & artifact ───────────────────────────
        os.makedirs(models_folder, exist_ok=True)
        timestamp = datetime.utcnow().strftime('%Y%m%d%H%M%S')
        uid = history.task_id[:8]

        model_path = os.path.join(models_folder, f"model_{model_type}_{timestamp}_{uid}.joblib")
        joblib.dump(pipeline, model_path)
        

        artifact = {
            'feature_names': FITUR_STRESS + FITUR_MOTIVASI + FITUR_DEMO,
            'bins_stress': bins_stress.tolist(),          # <-- pastikan list Python
            'bins_motivasi': bins_motivasi.tolist(),  
            'label_map': {0: 'Rendah', 1: 'Sedang', 2: 'Tinggi'},
            'demo_categories': {
                'Jurusan': cats_jurusan,
                'Gender': cats_gender,
                'freq_olahraga': cats_olahraga,
                'durasi_tidur': cats_tidur
            },
            'params': params
        }

        thresholds = {
            "bins_stress": bins_stress.tolist(),
            "bins_motivasi": bins_motivasi.tolist()
        }
        artifact_json = json.dumps(artifact) 

        artifact_path = model_path.replace('.joblib', '_meta.joblib')
        joblib.dump(artifact, artifact_path)

        # ── 10. Simpan record ke database ────────────────────────
        for mtype in ['stress', 'motivasi']:
            report = report_stress if mtype == 'stress' else report_motivasi

            # Ambil metrik rata-rata (weighted avg) – bisa juga macro avg
            precision = round(report['weighted avg']['precision'], 4)
            recall = round(report['weighted avg']['recall'], 4)
            f1 = round(report['weighted avg']['f1-score'], 4) 

            model_record = MLModel(
                type=mtype,
                algorithm='RandomForest',
                version=f"v_{timestamp}",
                file_path=model_path,
                is_active=False,
                accuracy=metrics[f'accuracy_{mtype}'],
                precision_score=precision,    # <-- diambil dari report
                recall_score=recall,          # <-- diambil dari report
                f1_score=f1,  
                data_count=len(df),                    # ← perbaikan
                qcut_thresholds=json.dumps(thresholds), # ← baru
                artifact_metadata=artifact_json,  
                created_at=datetime.utcnow()
            )
            db.session.add(model_record)
            db.session.flush()                     # ⬅️ dapatkan ID
            if mtype == model_type:                # ⬅️ hanya model yang sesuai training
                history.model_id = model_record.id

        history.status = "completed"
        history.metrics = json.dumps(metrics)
        history.progress_message = json.dumps({"progress": 100, "message": "Selesai"})
        db.session.commit()

    except Exception as e:
        current_app.logger.error(f"Training failed: {e}")
        history.status = "failed"
        history.progress_message = json.dumps({"progress": 0, "message": str(e)})
        db.session.commit()