# Testing Endpoint Prediksi di Postman

## 📋 Prerequisites

Sebelum test, pastikan:
1. ✅ Backend sudah running (`flask run`)
2. ✅ Model sudah tersimpan di database (`python scripts/save_model_to_db.py`)
3. ✅ User (mahasiswa) sudah terdaftar

---

## 🔐 Step 1: Login (Get JWT Token)

**Method**: POST  
**URL**: `http://localhost:5000/api/auth/login`  
**Body** (JSON):
```json
{
  "email": "mahasiswa@example.com",
  "password": "password123"
}
```

**Response** (Copy token untuk step berikutnya):
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "user": {
    "Id_User": 1,
    "email": "mahasiswa@example.com",
    "role": "mahasiswa",
    "mahasiswa": {
      "NIM": "220601001",
      "nama": "Budi Santoso",
      ...
    }
  }
}
```

---

## 👤 Step 2: Update Profile (Opsional - jika data belum lengkap)

**Method**: PUT  
**URL**: `http://localhost:5000/api/mahasiswa/profil`  
**Headers**:
```
Authorization: Bearer {ACCESS_TOKEN}
Content-Type: application/json
```

**Body** (JSON):
```json
{
  "angkatan": 2022,
  "gender": "laki-laki",
  "usia": 21,
  "freq_olahraga": "1-2 kali",
  "durasi_tidur": "6-7 Jam",
  "IPK": 3.5
}
```

**Response**:
```json
{
  "message": "Profil berhasil diperbarui.",
  "data": {
    "NIM": "220601001",
    "nama": "Budi Santoso",
    "angkatan": 2022,
    "gender": "laki-laki",
    "usia": 21,
    "freq_olahraga": "1-2 kali",
    "durasi_tidur": "6-7 Jam",
    "IPK": 3.5,
    ...
  }
}
```

---

## ✅ Step 3: Cek Profile Status

**Method**: GET  
**URL**: `http://localhost:5000/api/mahasiswa/profil/status`  
**Headers**:
```
Authorization: Bearer {ACCESS_TOKEN}
```

**Response**:
```json
{
  "is_complete": true,
  "missing_fields": []
}
```

Jika `is_complete: true`, profil sudah lengkap dan bisa submit kuesioner ✅

---

## 📝 Step 4: Submit Kuesioner (Prediksi)

**Method**: POST  
**URL**: `http://localhost:5000/api/mahasiswa/kuesioner`  
**Headers**:
```
Authorization: Bearer {ACCESS_TOKEN}
Content-Type: application/json
```

**Body** (JSON - Jawaban S1-S40 + M1-M28):

```json
{
  "jawaban": {
    "S1": 2,
    "S2": 3,
    "S3": 1,
    "S4": 2,
    "S5": 3,
    "S6": 2,
    "S7": 1,
    "S8": 2,
    "S9": 3,
    "S10": 2,
    "S11": 1,
    "S12": 2,
    "S13": 3,
    "S14": 2,
    "S15": 1,
    "S16": 2,
    "S17": 3,
    "S18": 2,
    "S19": 1,
    "S20": 2,
    "S21": 3,
    "S22": 2,
    "S23": 1,
    "S24": 2,
    "S25": 3,
    "S26": 2,
    "S27": 1,
    "S28": 2,
    "S29": 3,
    "S30": 2,
    "S31": 1,
    "S32": 2,
    "S33": 3,
    "S34": 2,
    "S35": 1,
    "S36": 2,
    "S37": 3,
    "S38": 2,
    "S39": 1,
    "S40": 2,
    "M1": 3,
    "M2": 4,
    "M3": 3,
    "M4": 4,
    "M5": 3,
    "M6": 4,
    "M7": 3,
    "M8": 4,
    "M9": 3,
    "M10": 4,
    "M11": 3,
    "M12": 4,
    "M13": 3,
    "M14": 4,
    "M15": 3,
    "M16": 4,
    "M17": 3,
    "M18": 4,
    "M19": 3,
    "M20": 4,
    "M21": 3,
    "M22": 4,
    "M23": 3,
    "M24": 4,
    "M25": 3,
    "M26": 4,
    "M27": 3,
    "M28": 4
  }
}
```

**Response**:
```json
{
  "message": "Kuesioner berhasil disimpan.",
  "Id_skrining": 5,
  "tingkat_stres": "Sedang",
  "tingkat_motivasi": "Tinggi",
  "score_stress": 85.5,
  "score_sdi": 3.2,
  "saran": "Tingkat stres Anda sedang, pertimbangkan untuk meningkatkan aktivitas fisik..."
}
```

✅ **Data demografis sudah otomatis diambil dari profile:**
- IPK: 3.5
- Usia: 21
- Angkatan: 2022
- Gender: laki-laki
- freq_olahraga: 1-2 kali
- durasi_tidur: 6-7 Jam
- Jurusan: Dari relasi ke tabel jurusan

---

## 📊 Step 5: Cek Hasil Skrining

**Method**: GET  
**URL**: `http://localhost:5000/api/mahasiswa/hasil/{NIM}`  
**Headers**:
```
Authorization: Bearer {ACCESS_TOKEN}
```

Contoh: `http://localhost:5000/api/mahasiswa/hasil/220601001`

**Response**:
```json
{
  "Id_skrining": 5,
  "NIM": "220601001",
  "tanggal_skrining": "2026-05-05T15:30:00",
  "tingkat_stres": "Sedang",
  "tingkat_motivasi": "Tinggi",
  "score_stress": 85.5,
  "score_sdi": 3.2,
  "saran": "Tingkat stres Anda sedang...",
  "input_jawaban": {...}
}
```

---

## 📜 Step 6: Lihat Riwayat Skrining

**Method**: GET  
**URL**: `http://localhost:5000/api/mahasiswa/history?page=1&per_page=10`  
**Headers**:
```
Authorization: Bearer {ACCESS_TOKEN}
```

**Response**:
```json
{
  "data": [
    {
      "Id_skrining": 5,
      "NIM": "220601001",
      "tanggal_skrining": "2026-05-05T15:30:00",
      "tingkat_stres": "Sedang",
      "tingkat_motivasi": "Tinggi",
      ...
    },
    {
      "Id_skrining": 4,
      "NIM": "220601001",
      "tanggal_skrining": "2026-05-04T14:20:00",
      "tingkat_stres": "Rendah",
      "tingkat_motivasi": "Sedang",
      ...
    }
  ],
  "total": 2,
  "page": 1,
  "total_pages": 1
}
```

---

## 💡 Postman Collection (Import Ini)

Buat file `postman_collection.json` dan import ke Postman:

```json
{
  "info": {
    "name": "TUGAS AKHIR - Prediksi Stress & Motivasi",
    "version": "1.0"
  },
  "item": [
    {
      "name": "1. Login",
      "request": {
        "method": "POST",
        "header": [{"key": "Content-Type", "value": "application/json"}],
        "url": {"raw": "http://localhost:5000/api/auth/login", "protocol": "http", "host": ["localhost"], "port": ["5000"], "path": ["api", "auth", "login"]},
        "body": {
          "mode": "raw",
          "raw": "{\"email\": \"mahasiswa@example.com\", \"password\": \"password123\"}"
        }
      }
    },
    {
      "name": "2. Update Profile",
      "request": {
        "method": "PUT",
        "header": [
          {"key": "Authorization", "value": "Bearer {{access_token}}"},
          {"key": "Content-Type", "value": "application/json"}
        ],
        "url": {"raw": "http://localhost:5000/api/mahasiswa/profil", "protocol": "http", "host": ["localhost"], "port": ["5000"], "path": ["api", "mahasiswa", "profil"]},
        "body": {
          "mode": "raw",
          "raw": "{\"angkatan\": 2022, \"gender\": \"laki-laki\", \"usia\": 21, \"freq_olahraga\": \"1-2 kali\", \"durasi_tidur\": \"6-7 Jam\", \"IPK\": 3.5}"
        }
      }
    },
    {
      "name": "3. Check Profile Status",
      "request": {
        "method": "GET",
        "header": [{"key": "Authorization", "value": "Bearer {{access_token}}"}],
        "url": {"raw": "http://localhost:5000/api/mahasiswa/profil/status", "protocol": "http", "host": ["localhost"], "port": ["5000"], "path": ["api", "mahasiswa", "profil", "status"]}
      }
    },
    {
      "name": "4. Submit Kuesioner",
      "request": {
        "method": "POST",
        "header": [
          {"key": "Authorization", "value": "Bearer {{access_token}}"},
          {"key": "Content-Type", "value": "application/json"}
        ],
        "url": {"raw": "http://localhost:5000/api/mahasiswa/kuesioner", "protocol": "http", "host": ["localhost"], "port": ["5000"], "path": ["api", "mahasiswa", "kuesioner"]},
        "body": {
          "mode": "raw",
          "raw": "{\"jawaban\": {\"S1\": 2, \"S2\": 3, \"S3\": 1, \"S4\": 2, \"S5\": 3, \"S6\": 2, \"S7\": 1, \"S8\": 2, \"S9\": 3, \"S10\": 2, \"S11\": 1, \"S12\": 2, \"S13\": 3, \"S14\": 2, \"S15\": 1, \"S16\": 2, \"S17\": 3, \"S18\": 2, \"S19\": 1, \"S20\": 2, \"S21\": 3, \"S22\": 2, \"S23\": 1, \"S24\": 2, \"S25\": 3, \"S26\": 2, \"S27\": 1, \"S28\": 2, \"S29\": 3, \"S30\": 2, \"S31\": 1, \"S32\": 2, \"S33\": 3, \"S34\": 2, \"S35\": 1, \"S36\": 2, \"S37\": 3, \"S38\": 2, \"S39\": 1, \"S40\": 2, \"M1\": 3, \"M2\": 4, \"M3\": 3, \"M4\": 4, \"M5\": 3, \"M6\": 4, \"M7\": 3, \"M8\": 4, \"M9\": 3, \"M10\": 4, \"M11\": 3, \"M12\": 4, \"M13\": 3, \"M14\": 4, \"M15\": 3, \"M16\": 4, \"M17\": 3, \"M18\": 4, \"M19\": 3, \"M20\": 4, \"M21\": 3, \"M22\": 4, \"M23\": 3, \"M24\": 4, \"M25\": 3, \"M26\": 4, \"M27\": 3, \"M28\": 4}}"
        }
      }
    },
    {
      "name": "5. Get Hasil",
      "request": {
        "method": "GET",
        "header": [{"key": "Authorization", "value": "Bearer {{access_token}}"}],
        "url": {"raw": "http://localhost:5000/api/mahasiswa/hasil/220601001", "protocol": "http", "host": ["localhost"], "port": ["5000"], "path": ["api", "mahasiswa", "hasil", "220601001"]}
      }
    },
    {
      "name": "6. Get History",
      "request": {
        "method": "GET",
        "header": [{"key": "Authorization", "value": "Bearer {{access_token}}"}],
        "url": {"raw": "http://localhost:5000/api/mahasiswa/history?page=1&per_page=10", "protocol": "http", "host": ["localhost"], "port": ["5000"], "path": ["api", "mahasiswa", "history"], "query": [{"key": "page", "value": "1"}, {"key": "per_page", "value": "10"}]}
      }
    }
  ],
  "variable": [
    {
      "key": "access_token",
      "value": "",
      "type": "string"
    }
  ]
}
```

---

## 🔧 Setup di Postman

1. **Import Collection**:
   - Buka Postman → Import → Paste JSON di atas
   
2. **Set Environment Variable**:
   - Buka collection → Variables
   - Isi `access_token` setelah login

3. **Run Step by Step**:
   - ✅ Login → Copy token → Paste di variable
   - ✅ Update Profile (opsional)
   - ✅ Check Profile Status
   - ✅ Submit Kuesioner
   - ✅ Get Hasil
   - ✅ Get History

---

## ⚡ Expected Flow

```
Login (Token)
    ↓
Update Profile (optional - if needed)
    ↓
Check Profile Status (verify is_complete=true)
    ↓
Submit Kuesioner (S1-S40 + M1-M28)
    ↓
Backend:
    - Ambil data demografi dari profile mahasiswa
    - Validasi jawaban
    - Prediksi menggunakan pipeline
    - Simpan hasil ke database
    ↓
Response dengan:
    - tingkat_stres: "Rendah", "Sedang", "Tinggi"
    - tingkat_motivasi: "Rendah", "Sedang", "Tinggi"
    - saran: "Rekomendasi berdasarkan hasil"
```

---

## 🐛 Debugging

### Jika error "Profile tidak lengkap"
```
❌ error: "Profil Anda belum lengkap..."
```
**Solution**: 
1. GET `/api/mahasiswa/profil/status`
2. Lihat `missing_fields`
3. PUT `/api/mahasiswa/profil` dengan field yang missing

### Jika error "Validasi stres"
```
❌ error: "Validasi stres: Missing required question S1"
```
**Solution**: 
- Pastikan semua jawaban S1-S40 ada di JSON
- Value harus 1-4 (integer)

### Jika error "Model tidak tersedia"
```
❌ tingkat_stres: "Rendah" (fallback), tingkat_motivasi: "Sedang" (fallback)
```
**Solution**:
- Jalankan `python scripts/save_model_to_db.py`
- Cek database: `MLModel.query.filter_by(is_active=True).all()`

---

## ✅ Checklist Testing

- [ ] Backend running
- [ ] Model tersimpan di database
- [ ] User mahasiswa tersedia
- [ ] Login berhasil & dapat token
- [ ] Profile lengkap (angkatan, gender, usia, freq_olahraga, durasi_tidur, IPK)
- [ ] Submit kuesioner dengan 40 jawaban S + 28 jawaban M
- [ ] Response berisi prediksi tingkat_stres & tingkat_motivasi
- [ ] Data hasil tersimpan di database
- [ ] Bisa query hasil & history

