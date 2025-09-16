from datetime import datetime

from flask import Flask
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:dumengtian463@localhost/hospital8'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)


class Doctor(db.Model):
    __tablename__ = 'doctor'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    speciality = db.Column(db.String(50), nullable=False)
    # title = db.Column(db.String(50))
    # introduction = db.Column(db.Text)
    # rating = db.Column(db.Float)
    department_id = db.Column(db.Integer, nullable=False)
    rating = db.Column(db.Integer, nullable=False)
    picture = db.Column(db.String(50), nullable=False)

class Patient(db.Model):
    __tablename__ = 'patient'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), nullable=False)
    age = db.Column(db.Integer)
    gender = db.Column(db.String(10))
    create_time = db.Column(db.DateTime)


class UserBrowseHistory(db.Model):
    __tablename__ = 'user_browse_history'
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patient.id'), nullable=False)
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctor.id'), nullable=False)
    browse_time = db.Column(db.DateTime, default=datetime.utcnow)


def recommend_doctors_by_browse_history(patient_id):
    with app.app_context():
        browse_history = UserBrowseHistory.query.filter_by(patient_id=patient_id).all()
        print(browse_history)
        if not browse_history:
            return []

        recommended_doctors = []
        for history in browse_history:
            doctor = Doctor.query.get(history.doctor_id)
            if doctor:
                similar_doctors = Doctor.query.filter(
                    Doctor.speciality == doctor.speciality,
                    Doctor.id != doctor.id
                ).all()
                for similar_doc in similar_doctors:
                    recommended_doctors.append({
                        'id': similar_doc.id,
                        'name': similar_doc.name,
                        'speciality': similar_doc.speciality,
                        'rating': similar_doc.rating,
                        'picture': similar_doc.picture
                        # 'title': similar_doc.title,
                        # 'introduction': similar_doc.introduction,
                        # 'rating': similar_doc.rating
                    })

        # 去重
        unique_recommended_doctors = []
        for doc in recommended_doctors:
            if doc not in unique_recommended_doctors:
                unique_recommended_doctors.append(doc)

        return unique_recommended_doctors


def get_patient_info(patient_id):
    with app.app_context():
        patient = Patient.query.get(patient_id)
        if patient:
            return {
                'id': patient.id,
                'name': patient.username,
                'age': patient.age,
                'gender': patient.gender,
                'registration_date': patient.create_time.strftime('%Y-%m-%d') if patient.create_time else "未知"
            }
        return None

def get_browsed_doctors(patient_id):
    """根据浏览历史，输出患者浏览过的所有医生的详细信息"""
    with app.app_context():
        # 第一步：查这个患者浏览过哪些医生的 doctor_id
        browse_history = UserBrowseHistory.query.filter_by(patient_id=patient_id).all()
        doctor_ids = list(set([history.doctor_id for history in browse_history]))

        print(f"患者{patient_id}浏览过的doctor_id有: {doctor_ids}")

        # 第二步：根据 doctor_id 批量查 doctor 表
        if doctor_ids:
            doctors = Doctor.query.filter(Doctor.id.in_(doctor_ids)).all()

            doctor_list = []
            for doctor in doctors:
                doctor_list.append({
                    'id': doctor.id,
                    'name': doctor.name,
                    'speciality': doctor.speciality,
                    'department_id': doctor.department_id,
                    'rating': doctor.rating,
                    'picture': doctor.picture
                    # 如果有其它字段，比如title、rating可以加上
                })

            print(f"浏览过的医生详细信息：{doctor_list}")
            return doctor_list
        else:
            print(f"患者{patient_id}没有浏览历史")
            return []

