from app.extensions import db

class KuesionerQuestion(db.Model):
    __tablename__ = "kuesioner_questions"
    
    id = db.Column(db.Integer, primary_key=True)
    question_text = db.Column(db.Text, nullable=False)
    category = db.Column(db.Enum("demografi", "stress", "motivation"), nullable=False)
    order_num = db.Column(db.Integer, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=db.func.current_timestamp())

class KuesionerOption(db.Model):
    __tablename__ = "kuesioner_options"
    
    id = db.Column(db.Integer, primary_key=True)
    question_id = db.Column(db.Integer, db.ForeignKey("kuesioner_questions.id"), nullable=False)
    option_text = db.Column(db.String(255), nullable=False)
    option_value = db.Column(db.Integer, nullable=False)
    order_num = db.Column(db.Integer, nullable=False)