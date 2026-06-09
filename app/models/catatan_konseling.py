from datetime import datetime
from app.extensions import db

class CatatanKonseling(db.Model):
    __tablename__ = "catatan_konseling"

    Id_catatan = db.Column(db.Integer, primary_key=True)
    NIM = db.Column(db.String(20), db.ForeignKey("mahasiswa.NIM"), nullable=False)
    NIP = db.Column(db.String(20), db.ForeignKey("dosen.NIP"), nullable=False)
    isi_catatan = db.Column(db.Text, nullable=False)
    tanggal_catat = db.Column(db.DateTime, default=datetime.utcnow)
    
    # 🔥 TAMBAHKAN 2 KOLOM UNTUK REPLY
    reply = db.Column(db.Text, nullable=True)
    tanggal_reply = db.Column(db.DateTime, nullable=True)

    # Relasi
    mahasiswa = db.relationship("Mahasiswa", back_populates="catatan")
    dosen = db.relationship("Dosen", back_populates="catatan_list")

    def to_dict(self):
        return {
            "Id_catatan": self.Id_catatan,
            "NIM": self.NIM,
            "NIP": self.NIP,
            "isi_catatan": self.isi_catatan,
            "tanggal_catat": self.tanggal_catat.isoformat() if self.tanggal_catat else None,
            # 🔥 TAMBAHKAN FIELD REPLY
            "reply": self.reply,
            "tanggal_reply": self.tanggal_reply.isoformat() if self.tanggal_reply else None,
            "status": "sudah_dibalas" if self.reply else "belum_dibalas"
        }