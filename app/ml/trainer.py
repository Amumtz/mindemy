# app/ml/trainer.py
import os, json, joblib, time
import pandas as pd
import numpy as np
from datetime import datetime
from sklearn.model_selection import train_test_split, GridSearchCV
from sklearn.pipeline import Pipeline
from sklearn.compose import ColumnTransformer
from sklearn.decomposition import PCA
from sklearn.preprocessing import OneHotEncoder, StandardScaler, LabelEncoder
from sklearn.ensemble import RandomForestClassifier
from sklearn.multioutput import MultiOutputClassifier
from sklearn.metrics import make_scorer, f1_score, accuracy_score, precision_score, recall_score, hamming_loss
from app import db
from app.models import Mahasiswa, Kuesioner, MLModel
from app.ml.predictor import registry


def avg_macro_f1(y_true, y_pred):
    """Rata‑rata macro F1 untuk dua target (stres & motivasi)."""
    f1_s = f1_score(y_true[:, 0], y_pred[:, 0], average='macro')
    f1_m = f1_score(y_true[:, 1], y_pred[:, 1], average='macro')
    return (f1_s + f1_m) / 2


# ──────────────────────────────────────────────
# 1. Fungsi persiapan data dari DATABASE (asli)
# ──────────────────────────────────────────────
def prepare_training_data():
    rows = []
    mhs_all = Mahasiswa.query.join(Kuesioner).all()
    if not mhs_all:
        raise ValueError("Tidak ada data training (mahasiswa + kuesioner)")

    for mhs in mhs_all:
        row = {
            'Jurusan': mhs.jurusan if mhs.jurusan else '',
            'Angkatan': mhs.angkatan if mhs.angkatan else 2023,
            'Gender': mhs.gender if mhs.gender else '',
            'Usia': mhs.usia if mhs.usia else 20,
            'IPK': mhs.ipk if mhs.ipk else 3.0,
            'freq_olahraga': mhs.freq_olahraga if mhs.freq_olahraga else '',
            'durasi_tidur': mhs.durasi_tidur if mhs.durasi_tidur else '',
        }
        for i in range(1, 41):
            row[f'S{i}'] = getattr(mhs.kuesioner, f'S{i}', 0)
        for i in range(1, 29):
            row[f'M{i}'] = getattr(mhs.kuesioner, f'M{i}', 0)

        rows.append(row)

    df = pd.DataFrame(rows)

    # Proses label (sama seperti di notebook)
    df['total_stress'] = df[[f'S{i}' for i in range(1, 41)]].sum(axis=1)
    df['label_stress'], bins_stress = pd.qcut(
        df['total_stress'], q=3,
        labels=["Rendah", "Sedang", "Tinggi"],
        retbins=True
    )

    # Motivasi SDI
    df['mean_im_know'] = df[['M1', 'M2', 'M3', 'M4']].mean(axis=1)
    df['mean_im_acc']  = df[['M5', 'M6', 'M7', 'M8']].mean(axis=1)
    df['mean_im_stim'] = df[['M9', 'M10', 'M11', 'M12']].mean(axis=1)
    df['mean_identified'] = df[['M13', 'M14', 'M15', 'M16']].mean(axis=1)
    df['mean_introjected'] = df[['M17', 'M18', 'M19', 'M20']].mean(axis=1)
    df['mean_external'] = df[['M21', 'M22', 'M23', 'M24']].mean(axis=1)
    df['mean_amotivation'] = df[['M25', 'M26', 'M27', 'M28']].mean(axis=1)

    df['intrinsic_total'] = (df['mean_im_know'] + df['mean_im_acc'] + df['mean_im_stim']) / 3
    df['controlled_extrinsic'] = (df['mean_introjected'] + df['mean_external']) / 2
    df['score_sdi'] = (2 * df['intrinsic_total']) + (1 * df['mean_identified']) \
                      - (1 * df['controlled_extrinsic']) - (2 * df['mean_amotivation'])
    df['label_motivasi'], bins_motivasi = pd.qcut(
        df['score_sdi'], q=3,
        labels=["Rendah", "Sedang", "Tinggi"],
        retbins=True
    )

    # Encode label
    le_stress = LabelEncoder()
    le_motivasi = LabelEncoder()
    df['stress_enc'] = le_stress.fit_transform(df['label_stress'])
    df['motivasi_enc'] = le_motivasi.fit_transform(df['label_motivasi'])
    y = df[['stress_enc', 'motivasi_enc']].values

    # Fitur
    fitur_stress = [f'S{i}' for i in range(1, 41)]
    fitur_motivasi = [f'M{i}' for i in range(1, 29)]
    fitur_demo = ['Jurusan', 'Angkatan', 'Gender', 'Usia', 'IPK',
                  'freq_olahraga', 'durasi_tidur']
    X = df[fitur_stress + fitur_motivasi + fitur_demo]

    return (X, y,
            fitur_stress, fitur_motivasi, fitur_demo,
            bins_stress, bins_motivasi)


# ──────────────────────────────────────────────
# 2. Persiapan data dari FILE CSV (untuk Celery)
# ──────────────────────────────────────────────
def prepare_training_data_from_csv(csv_path):
    """
    Membaca CSV hasil upload (harus 75 kolom) dan menghasilkan
    X, y, bins, dan daftar fitur seperti dari database.
    """
    df = pd.read_csv(csv_path)
    # Validasi jumlah kolom
    expected_cols = 75
    if df.shape[1] != expected_cols:
        raise ValueError(f"Dataset harus memiliki {expected_cols} kolom, ditemukan {df.shape[1]}")

    # Identifikasi kolom S1..S40, M1..M28, dan demografi
    fitur_stress = [f'S{i}' for i in range(1, 41)]
    fitur_motivasi = [f'M{i}' for i in range(1, 29)]
    fitur_demo = ['Jurusan', 'Angkatan', 'Gender', 'Usia', 'IPK',
                  'freq_olahraga', 'durasi_tidur']

    # Hitung label stres
    df['total_stress'] = df[fitur_stress].sum(axis=1)
    df['label_stress'], bins_stress = pd.qcut(
        df['total_stress'], q=3,
        labels=["Rendah", "Sedang", "Tinggi"],
        retbins=True
    )

    # Hitung label motivasi (SDI)
    df['mean_im_know'] = df[['M1', 'M2', 'M3', 'M4']].mean(axis=1)
    df['mean_im_acc']  = df[['M5', 'M6', 'M7', 'M8']].mean(axis=1)
    df['mean_im_stim'] = df[['M9', 'M10', 'M11', 'M12']].mean(axis=1)
    df['mean_identified'] = df[['M13', 'M14', 'M15', 'M16']].mean(axis=1)
    df['mean_introjected'] = df[['M17', 'M18', 'M19', 'M20']].mean(axis=1)
    df['mean_external'] = df[['M21', 'M22', 'M23', 'M24']].mean(axis=1)
    df['mean_amotivation'] = df[['M25', 'M26', 'M27', 'M28']].mean(axis=1)

    df['intrinsic_total'] = (df['mean_im_know'] + df['mean_im_acc'] + df['mean_im_stim']) / 3
    df['controlled_extrinsic'] = (df['mean_introjected'] + df['mean_external']) / 2
    df['score_sdi'] = (2 * df['intrinsic_total']) + (1 * df['mean_identified']) \
                      - (1 * df['controlled_extrinsic']) - (2 * df['mean_amotivation'])
    df['label_motivasi'], bins_motivasi = pd.qcut(
        df['score_sdi'], q=3,
        labels=["Rendah", "Sedang", "Tinggi"],
        retbins=True
    )

    # Encode label
    le_stress = LabelEncoder()
    le_motivasi = LabelEncoder()
    df['stress_enc'] = le_stress.fit_transform(df['label_stress'])
    df['motivasi_enc'] = le_motivasi.fit_transform(df['label_motivasi'])
    y = df[['stress_enc', 'motivasi_enc']].values

    X = df[fitur_stress + fitur_motivasi + fitur_demo]

    return (X, y,
            fitur_stress, fitur_motivasi, fitur_demo,
            bins_stress, bins_motivasi)


# ──────────────────────────────────────────────
# 3. Training dari CSV (untuk dipanggil Celery)
# ──────────────────────────────────────────────
def train_model_from_csv(csv_path, models_folder, version, progress_callback=None, hyperparams=None):

    """
    Latih model dari file CSV, simpan artifact, kembalikan hasil
    yang siap digunakan oleh Celery task.

    progress_callback(pct, message) dipanggil untuk update progress ke DB.
    Return struktur:
    {
        "file_path": str,
        "data_count": int,
        "duration": float,
        "thresholds": {"stress": [...], "motivasi": [...]},
        "stress": {
            "accuracy": float, "precision_score": float,
            "recall_score": float, "f1_score": float
        },
        "motivasi": {
            "accuracy": float, "precision_score": float,
            "recall_score": float, "f1_score": float
        },
        "metrics": { ... },        # metrik gabungan untuk history
        "artifact_metadata": { ... }
    }
    """
    start_time = time.time()

    # Progress: baca data
    if progress_callback:
        progress_callback(10, "Membaca dataset dari CSV...")

    X, y, f_stress, f_motiv, f_demo, bins_s, bins_m = prepare_training_data_from_csv(csv_path)
    n_data = len(X)

    # Progress: preprocessing
    if progress_callback:
        progress_callback(25, "Membangun pipeline...")

    if hyperparams and hyperparams.get('strategy') == 'manual':
        # Gunakan parameter yang diberikan langsung
        params = hyperparams.get('params', {})
        n_estimators = params.get('n_estimators', 100)
        max_depth = params.get('max_depth', None)
        min_samples_split = params.get('min_samples_split', 2)
        class_weight = params.get('class_weight', 'balanced')
        
        base_rf = RandomForestClassifier(
            n_estimators=n_estimators,
            max_depth=max_depth,
            min_samples_split=min_samples_split,
            class_weight=class_weight,
            random_state=42
        )
        multi_rf = MultiOutputClassifier(base_rf)
        best_pipe = Pipeline([('preprocess', preprocessor), ('clf', multi_rf)])
        
        # Tidak perlu GridSearch
        if progress_callback:
            progress_callback(40, "Melatih model dengan parameter manual...")
        best_pipe.fit(X, y)   # langsung fit
        cv_f1_avg = None       # tidak ada CV score
        
    else:
        # GridSearch seperti biasa
        param_grid = {
            'clf__estimator__max_depth': [5, 8, None],
            'clf__estimator__min_samples_split': [4, 6],
            'preprocess__pca_stress__pca__n_components': [5, 7],
            'preprocess__pca_motivasi__pca__n_components': [4, 6],
        }
        scorer = make_scorer(avg_macro_f1)
        if progress_callback:
            progress_callback(40, "Menjalankan GridSearchCV...")
        grid = GridSearchCV(pipe, param_grid, cv=3, scoring=scorer, n_jobs=-1)
        grid.fit(X, y)
        best_pipe = grid.best_estimator_
        cv_f1_avg = grid.best_score_
    # Tuning (GridSearchCV)
    param_grid = {
        'clf__estimator__max_depth': [5, 8, None],
        'clf__estimator__min_samples_split': [4, 6],
        'preprocess__pca_stress__pca__n_components': [5, 7],
        'preprocess__pca_motivasi__pca__n_components': [4, 6],
    }
    scorer = make_scorer(avg_macro_f1)

    if progress_callback:
        progress_callback(40, "Melakukan hyperparameter tuning (GridSearchCV)...")
    grid = GridSearchCV(pipe, param_grid, cv=3, scoring=scorer,
                        n_jobs=-1, verbose=0)
    grid.fit(X, y)

    best_pipe = grid.best_estimator_
    cv_f1_avg = grid.best_score_

    # Evaluasi pada test split
    if progress_callback:
        progress_callback(70, "Evaluasi model pada test set...")
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )
    best_pipe.fit(X_train, y_train)  # re-fit dengan best params
    y_pred = best_pipe.predict(X_test)

    # Metrik per target
    # Stress
    acc_s = accuracy_score(y_test[:, 0], y_pred[:, 0])
    prec_s = precision_score(y_test[:, 0], y_pred[:, 0], average='macro')
    rec_s = recall_score(y_test[:, 0], y_pred[:, 0], average='macro')
    f1_s = f1_score(y_test[:, 0], y_pred[:, 0], average='macro')
    # Motivasi
    acc_m = accuracy_score(y_test[:, 1], y_pred[:, 1])
    prec_m = precision_score(y_test[:, 1], y_pred[:, 1], average='macro')
    rec_m = recall_score(y_test[:, 1], y_pred[:, 1], average='macro')
    f1_m = f1_score(y_test[:, 1], y_pred[:, 1], average='macro')

    # Demo categories untuk artifact
    ohe = best_pipe.named_steps['preprocess'].named_transformers_['demo']
    demo_cats = {
        col: list(cats)
        for col, cats in zip(f_demo, ohe.categories_)
    }

    # Bangun artifact lengkap
    artifact = {
        'pipeline': best_pipe,
        'feature_names': f_stress + f_motiv + f_demo,
        'bins_stress': {},          # tidak digunakan karena fitur numerik di PCA
        'bins_motivasi': {},
        'label_map': {0: 'Rendah', 1: 'Sedang', 2: 'Tinggi'},
        'demo_categories': demo_cats,
        'best_params': grid.best_params_,
        'cv_macro_f1': cv_f1_avg
    }

    # Simpan file
    os.makedirs(models_folder, exist_ok=True)
    filename = f"model_{version}.joblib"
    file_path = os.path.join(models_folder, filename)
    if progress_callback:
        progress_callback(85, "Menyimpan artifact model...")
    joblib.dump(artifact, file_path)

    duration = time.time() - start_time

    # Thresholds untuk qcut (disimpan ke DB)
    thresholds = {
        'stress': [float(x) for x in bins_s],
        'motivasi': [float(x) for x in bins_m]
    }

    # Metrik gabungan untuk history
    metrics_summary = {
        'cv_macro_f1_avg': cv_f1_avg,
        'stress': {'accuracy': acc_s, 'precision': prec_s, 'recall': rec_s, 'f1': f1_s},
        'motivasi': {'accuracy': acc_m, 'precision': prec_m, 'recall': rec_m, 'f1': f1_m},
    }

    artifact_metadata = {
        'feature_names': artifact['feature_names'],
        'demo_categories': demo_cats,
        'best_params': grid.best_params_,
        'cv_macro_f1_avg': cv_f1_avg,
    }

    return {
        'file_path': file_path,
        'data_count': n_data,
        'duration': duration,
        'thresholds': thresholds,
        'stress': {
            'accuracy': acc_s,
            'precision_score': prec_s,
            'recall_score': rec_s,
            'f1_score': f1_s
        },
        'motivasi': {
            'accuracy': acc_m,
            'precision_score': prec_m,
            'recall_score': rec_m,
            'f1_score': f1_m
        },
        'metrics': metrics_summary,
        'artifact_metadata': artifact_metadata
    }


# ──────────────────────────────────────────────
# 4. (Opsional) Training dari DATABASE (lama)
# ──────────────────────────────────────────────
def train_model(app):
    """
    Versi asli untuk training langsung dari database (tanpa CSV).
    Tetap dipertahankan untuk kemudahan maintenance internal.
    """
    with app.app_context():
        X, y, f_stress, f_motiv, f_demo, bins_s, bins_m = prepare_training_data()
        n_data = len(X)

        pca_stress = Pipeline([('scaler', StandardScaler()),
                               ('pca', PCA(n_components=5, random_state=42))])
        pca_motivasi = Pipeline([('scaler', StandardScaler()),
                                 ('pca', PCA(n_components=10, random_state=42))])
        preprocessor = ColumnTransformer([
            ('pca_stress', pca_stress, f_stress),
            ('pca_motivasi', pca_motivasi, f_motiv),
            ('demo', OneHotEncoder(drop='first', handle_unknown='ignore'), f_demo)
        ])
        base_rf = RandomForestClassifier(n_estimators=100, class_weight='balanced', random_state=42)
        multi_rf = MultiOutputClassifier(base_rf)
        pipe = Pipeline([('preprocess', preprocessor), ('clf', multi_rf)])

        param_grid = {
            'clf__estimator__max_depth': [5, 8, None],
            'clf__estimator__min_samples_split': [4, 6],
            'preprocess__pca_stress__pca__n_components': [5, 7],
            'preprocess__pca_motivasi__pca__n_components': [4, 6],
        }
        scorer = make_scorer(avg_macro_f1)
        grid = GridSearchCV(pipe, param_grid, cv=3, scoring=scorer, n_jobs=-1, verbose=0)
        grid.fit(X, y)
        best_pipe = grid.best_estimator_
        cv_f1_avg = grid.best_score_

        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
        best_pipe.fit(X_train, y_train)
        y_pred = best_pipe.predict(X_test)
        f1_stress = f1_score(y_test[:, 0], y_pred[:, 0], average='macro')
        f1_motiv = f1_score(y_test[:, 1], y_pred[:, 1], average='macro')

        ohe = best_pipe.named_steps['preprocess'].named_transformers_['demo']
        demo_cats = {col: list(cats) for col, cats in zip(f_demo, ohe.categories_)}

        artifact = {
            'pipeline': best_pipe,
            'feature_names': f_stress + f_motiv + f_demo,
            'bins_stress': {},
            'bins_motivasi': {},
            'label_map': {0: 'Rendah', 1: 'Sedang', 2: 'Tinggi'},
            'demo_categories': demo_cats,
            'best_params': grid.best_params_,
            'cv_macro_f1': cv_f1_avg
        }

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'model_{timestamp}.joblib'
        filepath = os.path.join('storage', 'models', filename)
        joblib.dump(artifact, filepath)

        MLModel.query.filter(
            MLModel.type.in_(['stress', 'motivasi']),
            MLModel.is_active == 1
        ).update({'is_active': 0})
        db.session.commit()

        qcut_json = json.dumps({
            'stress': [float(x) for x in bins_s],
            'motivasi': [float(x) for x in bins_m]
        })
        meta_json = json.dumps({'cv_macro_f1_avg': cv_f1_avg})

        new_stress = MLModel(
            type='stress',
            algorithm='RandomForest_BR_balanced',
            version=timestamp,
            accuracy=0.0,
            precision_score=0.0,
            recall_score=0.0,
            f1_score=round(f1_stress, 4),
            file_path=filepath,
            is_active=True,
            data_count=n_data,
            qcut_thresholds=qcut_json,
            artifact_metadata=meta_json,
            created_at=datetime.now()
        )
        new_motivasi = MLModel(
            type='motivasi',
            algorithm='RandomForest_BR_balanced',
            version=timestamp,
            accuracy=0.0,
            precision_score=0.0,
            recall_score=0.0,
            f1_score=round(f1_motiv, 4),
            file_path=filepath,
            is_active=True,
            data_count=n_data,
            qcut_thresholds=qcut_json,
            artifact_metadata=meta_json,
            created_at=datetime.now()
        )
        db.session.add(new_stress)
        db.session.add(new_motivasi)
        db.session.commit()

        registry.reload_from_db(app)
        return filepath, f1_stress, f1_motiv