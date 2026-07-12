from app.extensions import db

class Dosen(db.Model):
    __tablename__ = "dosen"

    NIP = db.Column(db.String(20), primary_key=True)
    nama_dosen = db.Column(db.String(100), nullable=False)
    jabatan = db.Column(db.String(100))
    Id_User = db.Column(db.Integer, db.ForeignKey("users.Id_User"), nullable=False, unique=True)

    # Relasi
    user = db.relationship("User", back_populates="dosen")
    mahasiswa_wali = db.relationship("Mahasiswa", back_populates="dosen_wali")
    catatan_list = db.relationship("CatatanKonseling", back_populates="dosen")

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
        
        # Normalisasi jabatan untuk frontend
        jabatan_raw = self.dosen.jabatan
        if jabatan_raw:
            if "kaprodi" in jabatan_raw.lower():
                data["jabatan"] = "kaprodi"
            elif "dosen wali" in jabatan_raw.lower():
                data["jabatan"] = "dosen wali"
            else:
                data["jabatan"] = jabatan_raw.lower().replace(" ", "_")
        else:
            data["jabatan"] = "dosen wali"
        
        print(f"DEBUG to_dict: jabatan = {data['jabatan']}")
    
    # Tambahkan data mahasiswa jika ada
    elif self.role == "mahasiswa" and self.mahasiswa:
        data["NIM"] = self.mahasiswa.NIM
        data["nama"] = self.mahasiswa.nama_mahasiswa
    
    return data
=======
    def to_dict(self):
        return {
            "NIP": self.NIP,
            "nama_dosen": self.nama_dosen,
            "jabatan": self.jabatan,
            "Id_User": self.Id_User,
        }
>>>>>>> 739bd89b5c85dd8759f5f30896c96b74b6781793
