import os
import sys

# Bypass ML imports untuk migration
sys.argv.append('db')

# Import extensions yang sudah ada
from app.extensions import db, migrate
from app import create_app

# Buat app context
app = create_app('development')

# Import semua models (biar terdaftar di db)
from app.models import (
    User,
    Jurusan, 
    Dosen,
    Mahasiswa,
    CatatanKonseling,
    RiwayatSkrining,
    MLModel,
    TrainingHistory,
    Dataset
)

print("✅ Models berhasil diimport")

with app.app_context():
    import shutil
    
    # Hapus folder migrations jika ada
    if os.path.exists('migrations'):
        print("🗑️  Menghapus folder migrations lama...")
        shutil.rmtree('migrations')
    
    # Hapus semua tabel di database
    print("🗑️  Membersihkan database...")
    try:
        import mysql.connector
        conn = mysql.connector.connect(
            host='localhost',
            user='root',
            password='',
            database='mindemy'
        )
        cursor = conn.cursor()
        cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
        cursor.execute("SHOW TABLES")
        tables = cursor.fetchall()
        
        for table in tables:
            try:
                cursor.execute(f"DROP TABLE IF EXISTS {table[0]}")
                print(f"   - Menghapus tabel: {table[0]}")
            except:
                pass
        
        cursor.execute("SET FOREIGN_KEY_CHECKS = 1")
        conn.commit()
        cursor.close()
        conn.close()
        print("✅ Database berhasil dibersihkan")
    except Exception as e:
        print(f"⚠️  Error cleanup: {e}")
    
    # Import flask-migrate functions
    from flask_migrate import init, migrate, upgrade
    
    # Inisialisasi migration
    print("\n📁 Inisialisasi migrations...")
    init()
    
    # Generate migration script
    print("\n🔄 Membuat migration script...")
    migrate(message="create_all_tables")
    
    # Apply ke database
    print("\n📊 Menjalankan migration ke database...")
    upgrade()
    
    # Cek hasil
    print("\n📋 Tabel yang berhasil dibuat:")
    try:
        conn = mysql.connector.connect(
            host='localhost',
            user='root',
            password='',
            database='mindemy'
        )
        cursor = conn.cursor()
        cursor.execute("SHOW TABLES")
        tables = cursor.fetchall()
        
        if len(tables) <= 1:
            print("   ⚠️  Hanya tabel alembic_version yang terbuat!")
            print("\n💡 Kemungkinan masalah:")
            print("   1. Model tidak menggunakan db.Model dari extensions")
            print("   2. Tabel sudah ada sebelumnya")
        else:
            for table in tables:
                print(f"   ✓ {table[0]}")
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"Error: {e}")
    
    print("\n✅ Migration selesai!")