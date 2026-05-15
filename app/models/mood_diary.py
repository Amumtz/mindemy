from app.extensions import db

class MoodEntry(db.Model):
    __tablename__ = "mood_entries"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    nim = db.Column(db.String(20), db.ForeignKey("mahasiswa.NIM"), nullable=False)
    date = db.Column(db.Date, nullable=False)
    mood_value = db.Column(db.Integer, nullable=False)   # 1-5
    created_at = db.Column(db.TIMESTAMP, default=db.func.current_timestamp())
    updated_at = db.Column(db.TIMESTAMP, default=db.func.current_timestamp(), onupdate=db.func.current_timestamp())

    # Relasi balik ke mahasiswa (opsional)
    mahasiswa = db.relationship("Mahasiswa", backref=db.backref("mood_entries", lazy=True))

    def to_dict(self):
        return {
            "id": self.id,
            "nim": self.nim,
            "date": self.date.isoformat() if self.date else None,
            "mood_value": self.mood_value,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }


class DiaryEntry(db.Model):
    __tablename__ = "diary_entries"

    id = db.Column(db.Integer, primary_key=True)
    nim = db.Column(db.String(20), db.ForeignKey("mahasiswa.NIM"), nullable=False)
    date = db.Column(db.Date, nullable=False)
    title = db.Column(db.String(255))   # tambahan
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.TIMESTAMP, default=db.func.current_timestamp())
    updated_at = db.Column(db.TIMESTAMP, default=db.func.current_timestamp(), onupdate=db.func.current_timestamp())

    def to_dict(self):
        return {
            "id": self.id,
            "nim": self.nim,
            "date": self.date.isoformat() if self.date else None,
            "title": self.title,
            "content": self.content,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }