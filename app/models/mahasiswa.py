from app.extensions import db

class Mahasiswa(db.Model):
    __tablename__ = "mahasiswa"

    NIM = db.Column(db.String(20), primary_key=True)
    nama_mahasiswa = db.Column(db.String(100), nullable=False)
    kelas = db.Column(db.String(20))
    id_jurusan = db.Column(db.Integer, db.ForeignKey("jurusan.Id_Jurusan"))
    IPK = db.Column(db.Numeric(3, 2), default=0.00)
    NIP_doswal = db.Column(db.String(20), db.ForeignKey("dosen.NIP"))
    Id_User = db.Column(db.Integer, db.ForeignKey("users.Id_User"), nullable=False, unique=True)
    foto_profil = db.Column(db.String(255), nullable=True)

    # Tambahan kolom demografi (jika sudah ditambahkan via migrasi)
    angkatan = db.Column(db.String(10))
    gender = db.Column(db.String(10))
    usia = db.Column(db.Integer)
    freq_olahraga = db.Column(db.String(20))
    durasi_tidur = db.Column(db.String(20))

    # Relasi
    user = db.relationship("User", back_populates="mahasiswa")
    jurusan = db.relationship("Jurusan", back_populates="mahasiswa_list")
    dosen_wali = db.relationship("Dosen", back_populates="mahasiswa_wali")
    riwayat = db.relationship("RiwayatSkrining", back_populates="mahasiswa")
    catatan = db.relationship("CatatanKonseling", back_populates="mahasiswa")

    def to_dict(self):
        return {
            "NIM": self.NIM,
            "nama_mahasiswa": self.nama_mahasiswa,
            "kelas": self.kelas,
            "id_jurusan": self.id_jurusan,
            "IPK": float(self.IPK) if self.IPK else None,
            "NIP_doswal": self.NIP_doswal,
            "Id_User": self.Id_User,
            "foto_profil": self.foto_profil,
            "angkatan": self.angkatan,
            "gender": self.gender,
            "usia": self.usia,
            "freq_olahraga": self.freq_olahraga,
            "durasi_tidur": self.durasi_tidur,
        }