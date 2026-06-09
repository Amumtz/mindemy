"""
app/api/kuesioner.py
────────────────────────────────────────────────────────
GET  /api/kuesioner/questions   – ambil semua soal beserta pilihan jawaban
"""

from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required
from app.extensions import db
from app.models.kuesioner import KuesionerQuestion, KuesionerOption

kuesioner_bp = Blueprint("kuesioner", __name__)

@kuesioner_bp.route("/questions", methods=["GET"])
@jwt_required()
def get_questions():
    """Ambil semua soal kuesioner yang aktif beserta pilihan jawabannya"""
    try:
        questions = KuesionerQuestion.query.filter_by(is_active=True).order_by(KuesionerQuestion.order_num).all()
        
        result = []
        for q in questions:
            options = KuesionerOption.query.filter_by(question_id=q.id).order_by(KuesionerOption.order_num).all()
            result.append({
                "id": q.id,
                "text": q.question_text,
                "category": q.category,
                "order": q.order_num,
                "options": [{"text": opt.option_text, "value": opt.option_value} for opt in options]
            })
        
        return jsonify(result), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500