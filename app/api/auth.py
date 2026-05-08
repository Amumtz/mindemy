"""
blueprints/auth.py (sekarang app/api/auth.py)
─────────────────────────────────────────────
POST /api/auth/login
POST /api/auth/refresh
POST /api/auth/logout
POST /api/auth/register   (admin only, for creating accounts)
GET  /api/auth/me
"""

from flask import Blueprint, request, jsonify
from flask_jwt_extended import (
    create_access_token, create_refresh_token,
    jwt_required, current_user, get_jwt,
)
from app.extensions import db
from app.models import User, Mahasiswa, Dosen

auth_bp = Blueprint("auth", __name__)

# Simple in-memory token blocklist (use Redis in production)
_blocklist: set = set()


@auth_bp.route("/login", methods=["POST"])
def login():
    data     = request.get_json(silent=True) or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")

    if not username or not password:
        return jsonify({"error": "Username dan password wajib diisi."}), 400

    user = User.query.filter_by(username=username).first()
    if not user or not user.check_password(password):
        return jsonify({"error": "Username atau password salah."}), 401

    # Build extra claims with profile info
    extra = _build_extra_claims(user)
    access  = create_access_token(identity=str(user.Id_User), additional_claims=extra)
    refresh = create_refresh_token(identity=str(user.Id_User))

    return jsonify({
        "access_token":  access,
        "refresh_token": refresh,
        "user":          user.to_dict() | extra,
    })


@auth_bp.route("/refresh", methods=["POST"])
@jwt_required(refresh=True)
def refresh():
    extra  = _build_extra_claims(current_user)
    access = create_access_token(identity=str(current_user.Id_User), additional_claims=extra)
    return jsonify({"access_token": access})


@auth_bp.route("/logout", methods=["POST"])
@jwt_required()
def logout():
    jti = get_jwt()["jti"]
    _blocklist.add(jti)
    return jsonify({"message": "Berhasil logout."})


@auth_bp.route("/me", methods=["GET"])
@jwt_required()
def me():
    extra = _build_extra_claims(current_user)
    return jsonify(current_user.to_dict() | extra)


@auth_bp.route("/register", methods=["POST"])
@jwt_required()
def register():
    if current_user.role != "admin":
        return jsonify({"error": "Hanya admin yang dapat mendaftarkan akun."}), 403

    data = request.get_json(silent=True) or {}
    required = ["username", "password", "role"]
    for f in required:
        if not data.get(f):
            return jsonify({"error": f"Field '{f}' wajib diisi."}), 400

    if User.query.filter_by(username=data["username"]).first():
        return jsonify({"error": "Username sudah digunakan."}), 409

    if data["role"] not in ("admin", "dosen", "mahasiswa"):
        return jsonify({"error": "Role tidak valid."}), 400

    user = User(username=data["username"], role=data["role"])
    user.set_password(data["password"])
    db.session.add(user)
    db.session.flush()  # get user.Id_User

    # Create linked profile
    if data["role"] == "mahasiswa" and data.get("NIM"):
        mhs = Mahasiswa(
            NIM=data["NIM"],
            nama_mahasiswa=data.get("nama", data["username"]),
            kelas=data.get("kelas"),
            id_jurusan=data.get("id_jurusan"),
            NIP_doswal=data.get("NIP_doswal"),
            Id_User=user.Id_User,
        )
        db.session.add(mhs)

    elif data["role"] == "dosen" and data.get("NIP"):
        dsn = Dosen(
            NIP=data["NIP"],
            nama_dosen=data.get("nama", data["username"]),
            jabatan=data.get("jabatan"),
            Id_User=user.Id_User,
        )
        db.session.add(dsn)

    db.session.commit()
    return jsonify({"message": "Akun berhasil dibuat.", "user_id": user.Id_User}), 201


# ── Helpers ──────────────────────────────────────────────────────

def _build_extra_claims(user: User) -> dict:
    claims = {"role": user.role}
    if user.role == "mahasiswa" and user.mahasiswa:
        claims["NIM"]  = user.mahasiswa.NIM
        claims["nama"] = user.mahasiswa.nama_mahasiswa
    elif user.role == "dosen" and user.dosen:
        claims["NIP"]  = user.dosen.NIP
        claims["nama"] = user.dosen.nama_dosen
    return claims