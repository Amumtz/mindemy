from app.extensions import db

class Jurusan(db.Model):
    __tablename__ = "jurusan"

    Id_Jurusan = db.Column(db.Integer, primary_key=True)
    nama_jurusan = db.Column(db.String(100), nullable=False)
    NIP_kaprodi = db.Column(db.String(20), nullable=True)   # FK ke Dosen (opsional, bisa null)

    # Relasi ke mahasiswa
    mahasiswa_list = db.relationship("Mahasiswa", back_populates="jurusan")

    # Relasi ke dosen sebagai kaprodi (jika diperlukan)
    # kaprodi = db.relationship("Dosen", foreign_keys=[NIP_kaprodi])

    def to_dict(self) -> dict:
        return {
            "Id_Jurusan": self.Id_Jurusan,
            "nama_jurusan": self.nama_jurusan,
            "NIP_kaprodi": self.NIP_kaprodi,
        }