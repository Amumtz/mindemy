from werkzeug.security import generate_password_hash, check_password_hash
from app.extensions import db

class User(db.Model):
    __tablename__ = "users"   # pastikan huruf kecil semua sesuai dump

    Id_User = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
<<<<<<< HEAD
    password = db.Column(db.String(255), nullable=False)
    role = db.Column(db.Enum("admin", "dosen", "mahasiswa"), nullable=False)
    created_at = db.Column(db.DateTime)
=======
    password = db.Column(db.String(255), nullable=False)  # NOT NULL - password sudah ada dari admin
    role = db.Column(db.Enum("admin", "dosen", "mahasiswa"), nullable=False)
    created_at = db.Column(db.DateTime)
    is_activated = db.Column(db.Boolean, default=False)  # TAMBAHKAN: field untuk status aktivasi
>>>>>>> 739bd89b5c85dd8759f5f30896c96b74b6781793

    # Relationship ke Mahasiswa (one-to-one)
    mahasiswa = db.relationship(
        "Mahasiswa",
        back_populates="user",
        uselist=False,
        foreign_keys="Mahasiswa.Id_User"   # eksplisit
    )

    # Relationship ke Dosen (one-to-one)
    dosen = db.relationship(
        "Dosen",
        back_populates="user",
        uselist=False,
        foreign_keys="Dosen.Id_User"
    )

    def set_password(self, plain_password):
        self.password = generate_password_hash(plain_password)

    def check_password(self, plain_password):
        return check_password_hash(self.password, plain_password)

<<<<<<< HEAD
    # C:\Users\maach\Documents\TA_Ghifarii\mindemy\app\models\user.py

    def to_dict(self) -> dict:
        data = {
            "Id_User": self.Id_User,
            "username": self.username,
            "role": self.role,
        }
        
        # Tambahkan data dosen jika ada
        if self.role == "dosen" and self.dosen:
            data["NIP"] = self.dosen.NIP
            data["nama"] = self.dosen.nama_dosen
            
            # Format jabatan untuk frontend
            jabatan_raw = self.dosen.jabatan
            if jabatan_raw:
                jabatan_formatted = jabatan_raw.lower().replace(" ", "_")
                data["jabatan"] = jabatan_formatted
            else:
                data["jabatan"] = "dosen_wali"
        
        # Tambahkan data mahasiswa jika ada
        elif self.role == "mahasiswa" and self.mahasiswa:
            data["NIM"] = self.mahasiswa.NIM
            data["nama"] = self.mahasiswa.nama_mahasiswa
        
        return data
=======
    def to_dict(self):
        return {
            "Id_User": self.Id_User,
            "username": self.username,
            "role": self.role,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "is_activated": self.is_activated,
        }
>>>>>>> 739bd89b5c85dd8759f5f30896c96b74b6781793
