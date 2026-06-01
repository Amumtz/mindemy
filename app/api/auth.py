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


@auth_bp.route("/reset-password", methods=["POST"])
def reset_password():
    data = request.get_json(silent=True) or {}
    username = data.get("username", "").strip()
    # Terima identity atau nim/nip
    identity = data.get("identity") or data.get("nim") or data.get("nip")
    if identity:
        identity = str(identity).strip()
    new_password = data.get("new_password", "")

    if not username or not identity or not new_password:
        return jsonify({"error": "Username, NIM/NIP, dan password baru wajib diisi."}), 400
    if len(new_password) < 6:
        return jsonify({"error": "Password baru minimal 6 karakter."}), 400

    user = User.query.filter_by(username=username).first()
    if not user:
        return jsonify({"error": "Username tidak ditemukan."}), 404

    # Verifikasi identity (NIM/NIP) berdasarkan role
    if user.role == "mahasiswa":
        if not user.mahasiswa or user.mahasiswa.NIM != identity:
            return jsonify({"error": "NIM tidak cocok dengan username tersebut."}), 403
    elif user.role == "dosen":
        if not user.dosen or user.dosen.NIP != identity:
            return jsonify({"error": "NIP tidak cocok dengan username tersebut."}), 403
    else:
        return jsonify({"error": "Role tidak valid."}), 400

    # Reset password
    user.set_password(new_password)
    db.session.commit()

    return jsonify({"message": "Password berhasil direset. Silakan login dengan password baru."})

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