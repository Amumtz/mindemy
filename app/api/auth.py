"""
blueprints/auth.py (sekarang app/api/auth.py)
─────────────────────────────────────────────
POST /api/auth/login
POST /api/auth/refresh
POST /api/auth/logout
POST /api/auth/register   (admin only, for creating accounts)
POST /api/auth/activation  (BARU - untuk aktivasi akun mahasiswa)
GET  /api/auth/me
"""

from flask import Blueprint, request, jsonify
from flask_jwt_extended import (
    create_access_token, create_refresh_token,
    jwt_required, current_user, get_jwt,
)
from app.extensions import db
from app.models import User, Mahasiswa, Dosen, Jurusan

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

    
    if not user:
        return jsonify({"error": "Username atau password salah."}), 401
    
    if not user.check_password(password):
        return jsonify({"error": "Username atau password salah."}), 401
    
    # ============ CEK STATUS AKTIVASI ============
    if not user.is_activated:
        return jsonify({
            "error": "Akun belum diaktivasi. Silakan aktivasi terlebih dahulu."
        }), 403
    # =============================================
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


def _build_extra_claims(user: User) -> dict:
    claims = {"role": user.role}
    
    print(f"DEBUG: User role = {user.role}")
    print(f"DEBUG: User dosen = {user.dosen}")
    
    # Ambil data dosen termasuk jabatan
    if user.role == "dosen" and user.dosen:
        claims["NIP"] = user.dosen.NIP
        claims["nama"] = user.dosen.nama_dosen
        
        # Normalisasi nilai jabatan untuk frontend
        jabatan_raw = user.dosen.jabatan
        if jabatan_raw:
            # Ubah ke lowercase dan replace spasi dengan underscore
            if "kaprodi" in jabatan_raw.lower():
                claims["jabatan"] = "kaprodi"
            elif "dosen wali" in jabatan_raw.lower() or "dosen_wali" in jabatan_raw.lower():
                claims["jabatan"] = "dosen_wali"
            else:
                # Default untuk jabatan lain
                claims["jabatan"] = jabatan_raw.lower().replace(" ", "_")
        else:
            claims["jabatan"] = "dosen_wali"  # Default untuk dosen biasa
        
        print(f"DEBUG: Original jabatan = {jabatan_raw}, Normalized = {claims['jabatan']}")
    
    elif user.role == "mahasiswa" and user.mahasiswa:
        claims["NIM"] = user.mahasiswa.NIM
        claims["nama"] = user.mahasiswa.nama_mahasiswa
    
    print(f"DEBUG: Final claims = {claims}")
    
    return claims

# @auth_bp.route("/reset-password", methods=["POST"])
# def reset_password():
#     data = request.get_json(silent=True) or {}
#     username = data.get("username", "").strip()
#     # Terima identity atau nim/nip
#     identity = data.get("identity") or data.get("nim") or data.get("nip")
#     if identity:
#         identity = str(identity).strip()
#     new_password = data.get("new_password", "")

#     if not username or not identity or not new_password:
#         return jsonify({"error": "Username, NIM/NIP, dan password baru wajib diisi."}), 400
#     if len(new_password) < 6:
#         return jsonify({"error": "Password baru minimal 6 karakter."}), 400

#     user = User.query.filter_by(username=username).first()
#     if not user:
#         return jsonify({"error": "Username tidak ditemukan."}), 404

#     # Verifikasi identity (NIM/NIP) berdasarkan role
#     if user.role == "mahasiswa":
#         if not user.mahasiswa or user.mahasiswa.NIM != identity:
#             return jsonify({"error": "NIM tidak cocok dengan username tersebut."}), 403
#     elif user.role == "dosen":
#         if not user.dosen or user.dosen.NIP != identity:
#             return jsonify({"error": "NIP tidak cocok dengan username tersebut."}), 403
#     else:
#         return jsonify({"error": "Role tidak valid."}), 400

#     # Reset password
#     user.set_password(new_password)
#     db.session.commit()

#     return jsonify({"message": "Password berhasil direset. Silakan login dengan password baru."})

# @auth_bp.route("/register", methods=["POST"])
# def register():
#     data = request.get_json(silent=True) or {}

#     # Ambil field identitas (bisa dikirim sebagai "identity" atau "nim" / "nip")
#     identity = data.get("identity") or data.get("nim") or data.get("nip")
#     username = data.get("username", "").strip()
#     password = data.get("password", "")

#     if not identity or not username or not password:
#         return jsonify({"error": "NIM/NIP, username, dan password wajib diisi."}), 400

    
#     if identity.isdigit() and len(identity) <= 12:
#         role = "dosen"
#         nip = identity
#         nim = None
#     else:
#         role = "mahasiswa"
#         nim = identity
#         nip = None

#     if User.query.filter_by(username=username).first():
#         return jsonify({"error": "Username sudah digunakan."}), 409

#     # Buat user
#     user = User(username=username, role=role)
#     user.set_password(password)
#     db.session.add(user)
#     db.session.flush()

#     # Buat profil dasar (hanya NIM/NIP, field lain null)
#     if role == "mahasiswa":
#         mhs = Mahasiswa(
#             NIM=nim,
#             nama_mahasiswa=None,   # akan diisi nanti
#             Id_User=user.Id_User
#         )
#         db.session.add(mhs)
#     else:
#         dsn = Dosen(
#             NIP=nip,
#             nama_dosen=None,
#             Id_User=user.Id_User
#         )
#         db.session.add(dsn)

#     db.session.commit()

#     # Langsung login? Atau beri pesan sukses & minta login.
#     return jsonify({
#         "message": "Registrasi berhasil. Silakan login untuk melengkapi profil.",
#         "user_id": user.Id_User,
#         "role": role
#     }), 201


# ============ ENDPOINT AKTIVASI ============

@auth_bp.route("/activation", methods=["POST"])
def activation():
    """
    Endpoint untuk aktivasi akun mahasiswa (verifikasi username & password yang sudah ada)
    Request body: { "username": "xxx", "password": "xxx" }
    """
    try:
        data = request.get_json(silent=True) or {}
        username = data.get("username", "").strip()
        password = data.get("password", "")
        
        if not username or not password:
            return jsonify({"error": "Username dan password wajib diisi."}), 400
        
        # Cari user berdasarkan username
        user = User.query.filter_by(username=username).first()
        
        if not user:
            return jsonify({"error": "Akun tidak ditemukan. Pastikan username Anda sudah terdaftar."}), 404
        
        # CEK APAKAH SUDAH AKTIVASI
        if user.is_activated:
            return jsonify({"error": "Akun sudah diaktivasi sebelumnya. Silakan login."}), 400
        
        # Verifikasi password
        if not user.check_password(password):
            return jsonify({"error": "Password salah. Periksa kembali."}), 401
        
        # Tandai user sebagai sudah diaktivasi
        user.is_activated = True
        
        # Ambil data mahasiswa
        nim = None
        nama = None
        jurusan = None
        angkatan = None
        kelas = None
        nip_doswal = None
        
        if user.role == "mahasiswa" and user.mahasiswa:
            nim = user.mahasiswa.NIM
            nama = user.mahasiswa.nama_mahasiswa
            kelas = user.mahasiswa.kelas
            angkatan = user.mahasiswa.angkatan
            nip_doswal = user.mahasiswa.NIP_doswal
            
            # Ambil nama jurusan dari tabel jurusan
            if user.mahasiswa.id_jurusan:
                jurusan_obj = Jurusan.query.filter_by(Id_Jurusan=user.mahasiswa.id_jurusan).first()
                if jurusan_obj:
                    jurusan = jurusan_obj.nama_jurusan
        
        db.session.commit()
        
        # Kembalikan data user
        return jsonify({
            "message": "Aktivasi berhasil",
            "user": {
                "username": user.username,
                "NIM": nim,
                "nama": nama or user.username,
                "jurusan": jurusan or "",
                "angkatan": angkatan or "",
                "kelas": kelas or "",
                "nip_doswal": nip_doswal or "",
            }
        }), 200
        
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": f"Terjadi kesalahan: {str(e)}"}), 500


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
