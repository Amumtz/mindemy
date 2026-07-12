from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, current_user
from sqlalchemy import func
from app.extensions import db
from app.models import Mahasiswa, RiwayatSkrining, CatatanKonseling

dosen_bp = Blueprint("dosen", __name__)


def dosen_required(fn):
    from functools import wraps
    @wraps(fn)
    @jwt_required()
    def wrapper(*args, **kwargs):
        if current_user.role not in ("dosen", "admin"):
            return jsonify({"error": "Akses ditolak."}), 403
        return fn(*args, **kwargs)
    return wrapper


def _get_nip() -> str:
    return current_user.dosen.NIP if current_user.role == "dosen" else request.args.get("NIP", "")


# ── Daftar mahasiswa bimbingan (Early Warning System Integrated) ──

@dosen_bp.route("/mahasiswa", methods=["GET"])
@dosen_required
def list_mahasiswa():
    nip = _get_nip()
    page    = request.args.get("page", 1, type=int)
    per     = request.args.get("per_page", 20, type=int)
    search  = request.args.get("q", "")

    q = Mahasiswa.query.filter_by(NIP_doswal=nip)
    if search:
        q = q.filter(
            (Mahasiswa.NIM.like(f"%{search}%")) |
            (Mahasiswa.nama_mahasiswa.like(f"%{search}%"))
        )
    paginated = q.paginate(page=page, per_page=per, error_out=False)

    result = []
    for mhs in paginated.items:
        riwayat_all = (
            RiwayatSkrining.query
            .filter_by(NIM=mhs.NIM)
            .order_by(RiwayatSkrining.tanggal_skrining.desc())
            .all()
        )
        
        item = mhs.to_dict()
        
        if riwayat_all:
            latest = riwayat_all[0]
            latest_dict = latest.to_dict()
            
            is_spike = False
            if len(riwayat_all) > 1:
                prev = riwayat_all[1]
                score_sekarang = latest.score_stress or 0
                score_sebelumnya = prev.score_stress or 0
                
                if (score_sekarang - score_sebelumnya) >= 30:
                    is_spike = True
            
            latest_dict["is_spike"] = is_spike
            item["last_skrining"] = latest_dict
        else:
            item["last_skrining"] = None
            
        result.append(item)

    return jsonify({
        "data":        result,
        "total":       paginated.total,
        "page":        paginated.page,
        "total_pages": paginated.pages,
    })


# ── Detail satu mahasiswa ─────────────────────────────────────────

@dosen_bp.route("/mahasiswa/<nim>", methods=["GET"])
@dosen_required
def detail_mahasiswa(nim: str):
    nip = _get_nip()
    mhs = Mahasiswa.query.get_or_404(nim)

    if current_user.role == "dosen" and mhs.NIP_doswal != nip:
        return jsonify({"error": "Mahasiswa bukan bimbingan Anda."}), 403

    riwayat = [r.to_dict() for r in mhs.riwayat]
    catatan = [c.to_dict() for c in mhs.catatan]

    return jsonify({
        "mahasiswa": mhs.to_dict(),
        "riwayat":   riwayat,
        "catatan":   catatan,
    })


# ── Statistik bimbingan (Sinkron Sesuai Daftar Mahasiswa Aktif) ──

@dosen_bp.route("/statistik", methods=["GET"])
@dosen_required
def statistik():
    nip  = _get_nip()
    
    # 1. Ambil semua NIM mahasiswa bimbingan aktif dosen ini saja
    nims = [m.NIM for m in Mahasiswa.query.filter_by(NIP_doswal=nip).all()]

    if not nims:
        return jsonify({
            "total_mahasiswa": 0,
            "sudah_skrining":  0,
            "stress_dist":     {"Rendah": 0, "Sedang": 0, "Tinggi": 0},
            "motivasi_dist":   {"Rendah": 0, "Sedang": 0, "Tinggi": 0},
        })

    # 2. Ambil baris riwayat skrining paling baru (latest) untuk masing-masing NIM mahasiswa bimbingan tersebut
    subq = (
        db.session.query(
            RiwayatSkrining.NIM,
            func.max(RiwayatSkrining.tanggal_skrining).label("max_tgl")
        )
        .filter(RiwayatSkrining.NIM.in_(nims))
        .group_by(RiwayatSkrining.NIM)
        .subquery()
    )
    latest_rows = (
        db.session.query(RiwayatSkrining)
        .join(subq, (RiwayatSkrining.NIM == subq.c.NIM) &
                    (RiwayatSkrining.tanggal_skrining == subq.c.max_tgl))
        .all()
    )

    # 3. Hitung distribusi skor secara presisi hanya dari baris data bimbingan aktif
    stress_dist   = {"Rendah": 0, "Sedang": 0, "Tinggi": 0}
    motivasi_dist = {"Rendah": 0, "Sedang": 0, "Tinggi": 0}
    
    for row in latest_rows:
        if row.tingkat_stres in stress_dist:
            stress_dist[row.tingkat_stres] += 1
        if row.tingkat_motivasi in motivasi_dist:
            motivasi_dist[row.tingkat_motivasi] += 1

    return jsonify({
        "total_mahasiswa": len(nims),
        "sudah_skrining":  len(latest_rows),
        "belum_skrining":  len(nims) - len(latest_rows),
        "stress_dist":     stress_dist,
        "motivasi_dist":   motivasi_dist,
    })


# ── Catatan konseling CRUD & Real-time Timestamp ──────────────────

@dosen_bp.route("/catatan", methods=["POST"])
@dosen_required
def tambah_catatan():
    nip  = current_user.dosen.NIP if current_user.role == "dosen" else request.get_json().get("NIP")
    data = request.get_json(silent=True) or {}

    nim        = data.get("NIM")
    isi_catatan= data.get("isi_catatan", "").strip()
    if not nim or not isi_catatan:
        return jsonify({"error": "NIM dan isi_catatan wajib diisi."}), 400

    mhs = Mahasiswa.query.get_or_404(nim)
    if current_user.role == "dosen" and mhs.NIP_doswal != nip:
        return jsonify({"error": "Mahasiswa bukan bimbingan Anda."}), 403

    # Field tanggal_catat otomatis terisi waktu real-time UTC via default=datetime.utcnow di model
    catatan = CatatanKonseling(NIM=nim, NIP=nip, isi_catatan=isi_catatan)
    db.session.add(catatan)
    db.session.commit()
    return jsonify({"message": "Catatan berhasil disimpan.", "id": catatan.Id_catatan}), 201


@dosen_bp.route("/catatan/<int:id_catatan>", methods=["PUT"])
@dosen_required
def edit_catatan(id_catatan):
    """Mengubah isi catatan bimbingan yang sudah ada."""
    nip = _get_nip()
    catatan = CatatanKonseling.query.get_or_404(id_catatan)
    
    if current_user.role == "dosen" and catatan.NIP != nip:
        return jsonify({"error": "Anda tidak memiliki hak akses mengubah catatan ini."}), 403
        
    data = request.get_json(silent=True) or {}
    isi_baru = data.get("isi_catatan", "").strip()
    
    if not isi_baru:
        return jsonify({"error": "Isi catatan tidak boleh kosong."}), 400
        
    catatan.isi_catatan = isi_baru
    db.session.commit()
    return jsonify({"message": "Catatan berhasil diperbarui."}), 200


@dosen_bp.route("/catatan/<int:id_catatan>", methods=["DELETE"])
@dosen_required
def hapus_catatan(id_catatan):
    """Menghapus catatan bimbingan dari basis data."""
    nip = _get_nip()
    catatan = CatatanKonseling.query.get_or_404(id_catatan)
    
    if current_user.role == "dosen" and catatan.NIP != nip:
        return jsonify({"error": "Anda tidak memiliki hak akses menghapus catatan ini."}), 403
        
    db.session.delete(catatan)
    db.session.commit()
    return jsonify({"message": "Catatan berhasil dihapus secara permanen."}), 200


@dosen_bp.route("/catatan/<nim>", methods=["GET"])
@dosen_required
def get_catatan(nim: str):
    mhs = Mahasiswa.query.get_or_404(nim)
    return jsonify([c.to_dict() for c in mhs.catatan])