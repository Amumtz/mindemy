import json
from datetime import datetime
from app.extensions import db

class RiwayatSkrining(db.Model):
    __tablename__ = "riwayat_skrining"

    Id_skrining = db.Column(db.Integer, primary_key=True)
    NIM = db.Column(db.String(20), db.ForeignKey("mahasiswa.NIM"), nullable=False)
    tanggal_skrining = db.Column(db.DateTime, default=datetime.utcnow)
    input_jawaban = db.Column(db.Text)   # JSON string
    tingkat_stres = db.Column(db.Enum("Rendah", "Sedang", "Tinggi"))
    tingkat_motivasi = db.Column(db.Enum("Rendah", "Sedang", "Tinggi"))
    saran = db.Column(db.Text)

    # --- Tambahan ---
    score_stress = db.Column(db.Integer, nullable=True)
    score_sdi = db.Column(db.Float, nullable=True)

    # Relasi
    mahasiswa = db.relationship("Mahasiswa", back_populates="riwayat")

    def get_jawaban(self) -> dict:
        """Mengembalikan jawaban dalam bentuk dictionary."""
        if self.input_jawaban:
            return json.loads(self.input_jawaban)
        return {}

    def to_dict(self) -> dict:
        return {
            "Id_skrining": self.Id_skrining,
            "NIM": self.NIM,
            "tanggal_skrining": self.tanggal_skrining.isoformat() if self.tanggal_skrining else None,
            "tingkat_stres": self.tingkat_stres,
            "tingkat_motivasi": self.tingkat_motivasi,
            "saran": self.saran,
            "score_stress": self.score_stress,
            "score_sdi": self.score_sdi,
        }