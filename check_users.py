# C:\Users\maach\Documents\TA_Ghifarii\mindemy\check_users.py

from app import create_app
from app.models import User

app = create_app()

with app.app_context():
    users = User.query.all()
    for user in users:
        print(f"ID: {user.Id_User}, Username: {user.username}, Role: {user.role}")
        if user.dosen:
            print(f"  -> NIP: {user.dosen.NIP}, Nama: {user.dosen.nama_dosen}, Jabatan: {user.dosen.jabatan}")
        print()