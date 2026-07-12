from app import create_app
from app.extensions import db
from app.models import User

app = create_app()

with app.app_context():
    print("\n[INFO] Memulai perbaikan password massal akun dosen...")
    
    # Masukkan budi_santoso ke dalam daftar perbaikan
    target_users = ["dosen_wali", "hendrag", "andiwijaya", "budi_santoso"]
    
    for username in target_users:
        user = User.query.filter_by(username=username).first()
        if user:
            user.set_password("password") # Membuat hash native lokal yang 100% valid
            print(f"[SUCCESS] Akun '{username}' berhasil diperbarui.")
        else:
            print(f"[WARNING] Akun '{username}' tidak ditemukan di tabel users.")

    # Simpan permanen perubahan ke MySQL
    db.session.commit()
    print("==========================================================")
    print("DATABASE SELESAI DIPERBAIKI SECARA MASSAL!")
    print("Semua akun dosen di atas sekarang bisa login dengan: password")
    print("==========================================================\n")