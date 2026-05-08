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

    def to_dict(self):
        return {
            "NIP": self.NIP,
            "nama_dosen": self.nama_dosen,
            "jabatan": self.jabatan,
            "Id_User": self.Id_User,
        }