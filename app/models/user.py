from werkzeug.security import generate_password_hash, check_password_hash
from app.extensions import db

class User(db.Model):
    __tablename__ = "users"   # pastikan huruf kecil semua sesuai dump

    Id_User = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    role = db.Column(db.Enum("admin", "dosen", "mahasiswa"), nullable=False)
    created_at = db.Column(db.DateTime)

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

    def to_dict(self):
        return {
            "Id_User": self.Id_User,
            "username": self.username,
            "role": self.role,
            "created_at": self.created_at.isoformat() if self.created_at else None
        }