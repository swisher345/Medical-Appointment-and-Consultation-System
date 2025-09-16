import io
import os
import random
import re
import traceback
from datetime import datetime
from datetime import timedelta
from functools import wraps

import pandas as pd
import pymysql
import pymysql.cursors
import pymysql.cursors
from flashtext import KeywordProcessor
from flask import Flask
from flask import flash
from flask import send_file
from flask_migrate import Migrate
from prophet import Prophet
# 情感分析函数
from snownlp import SnowNLP
from werkzeug.security import generate_password_hash, check_password_hash

import nlp  # 导入nlp.py模块
from analysis.appointment_departments import get_department_distribution, get_registration_trend
from analysis.appointment_details import get_registration_details
from analysis.appointment_summary import get_summary_data
from chatbot_graph import ChatBotGraph
from db_utils import get_object, get_objects  # 保留原有工具函数引用
from recommand import *  # 智能推荐
from routes.registration_data import get_registration_data
from search import *  # 你的搜索模块，确保存在并正确
from xunf import SpeechRecognizer


# 初始化Flask应用

def analyze_sentiment(comment):
    s = SnowNLP(comment)
    sentiment = s.sentiments  # 返回 0~1 的概率值（越接近1越积极）
    if sentiment > 0.6:      # 积极
        return '好'
    elif sentiment < 0.2:    # 消极
        return '差'
    else:                    # 中性
        return '中'
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:dumengtian463@localhost/hospital8?charset=utf8mb4'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
migrate = Migrate(app, db)
app.secret_key = '123456'





# 患者模型（原有）
class Patient(db.Model):
    __tablename__ = 'patient'
    id = db.Column(db.Integer, primary_key=True, comment='患者id')
    username = db.Column(db.String(50), nullable=False, comment='登录用户名')
    password = db.Column(db.String(100), nullable=False, comment='登录密码')
    gender = db.Column(db.SmallInteger, comment='性别 (0=男, 1=女)')
    age = db.Column(db.Integer, comment='年龄')
    phone = db.Column(db.String(20), unique=True, nullable=False, comment='联系电话')
    email = db.Column(db.String(100), unique=True, nullable=False, comment='电子邮箱')
    id_card = db.Column(db.String(18), comment='身份证号')
    login_type = db.Column(db.SmallInteger, comment='登录方式 (0=密码, 1=验证码)')
    last_login_time = db.Column(db.DateTime, comment='最后登录时间')
    status = db.Column(db.SmallInteger, comment='用户状态 (0=禁用, 1=正常)')
    medical_history = db.Column(db.Text, nullable=False, comment='病史记录')
    create_time = db.Column(db.DateTime, default=datetime.now, nullable=False, comment='创建时间')
    update_time = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, nullable=False,
                            comment='更新时间')

    def __repr__(self):
        return f'<Patient {self.username}>'


# 管理员（医生）模型（原有）
class Admin(db.Model):
    __tablename__ = 'admin'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    department_id = db.Column(db.Integer,  nullable=False)
    def __repr__(self):
        return f'<Admin {self.username}>'


# 定义科室模型，需与数据库表结构对应
class Department(db.Model):
    __tablename__ = 'department'  # 假设表名是 department
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50))
    parent_id = db.Column(db.Integer)
    service_hours = db.Column(db.String(100))
    description = db.Column(db.Text)
    create_time = db.Column(db.DateTime)
    update_time = db.Column(db.DateTime)
    location = db.Column(db.String(100))

# 医生模型（原有）
class Doctor(db.Model):
    __tablename__ = 'doctor'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    gender = db.Column(db.SmallInteger)
    title_id = db.Column(db.Integer)
    speciality = db.Column(db.String(1000))
    work_years = db.Column(db.Integer)
    phone = db.Column(db.String(20))
    email = db.Column(db.String(100))
    department_id = db.Column(db.Integer, db.ForeignKey('department.id'))
    work_date = db.Column(db.Date)
    picture = db.Column(db.String(255))
    age = db.Column(db.Integer)
    consultation_fee = db.Column(db.Numeric(6, 2))
    doctorintro = db.Column(db.String(1000))
    keyworks = db.Column(db.String(1000))
    meeting_number = db.Column(db.String(50), unique=True)  # 关联字段
    department = db.relationship('Department', backref=db.backref('doctors', lazy=True))


# 预约模型（原有）
class Appointment(db.Model):
    __tablename__ = 'appointment'
    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey('patient.id'))
    doctor_id = db.Column(db.Integer, db.ForeignKey('doctor.id'))
    department_id = db.Column(db.Integer, db.ForeignKey('department.id'))
    appointment_time = db.Column(db.DateTime)
    status = db.Column(db.SmallInteger, default=0, comment='0=预约成功,1=取消预约,2=修改预约,3=已完成')
    remark = db.Column(db.String(255))
    remind = db.Column(db.Integer, default=0, nullable=False, comment='提醒类型：0=无提醒,1=短信提醒,2=电话提醒')
    create_time = db.Column(db.DateTime, default=datetime.now, nullable=False, comment='创建时间')
    update_time = db.Column(db.DateTime, default=datetime.now, onupdate=datetime.now, nullable=False,
                            comment='更新时间')
    meeting_number = db.Column(db.String(50), db.ForeignKey('doctor.meeting_number'))  # 外键
    patient = db.relationship('Patient', backref=db.backref('appointments', lazy=True))
    doctor = db.relationship('Doctor', foreign_keys=[doctor_id], backref=db.backref('appointments', lazy=True))
    department = db.relationship('Department', backref=db.backref('appointments', lazy=True))


# 收费记录模型（原有）
class ChargeRecord(db.Model):
    __tablename__ = 'appointment_charge'
    id = db.Column(db.Integer, primary_key=True)
    appointment_id = db.Column(db.Integer, db.ForeignKey('appointment.id'), nullable=False)
    fee = db.Column(db.Numeric(6, 2), nullable=False)
    payment_status = db.Column(db.SmallInteger, default=0, nullable=False)  # 0=未支付, 1=已支付, 2=已退款
    charge_time = db.Column(db.DateTime, default=datetime.now, nullable=False)
    refund_time = db.Column(db.DateTime)
    appointment = db.relationship('Appointment', backref='charge_record')


# 用户浏览历史模型
class UserBrowseHistory(db.Model):
    __tablename__ = 'user_browse_history'
    id = db.Column(db.Integer, primary_key=True, comment='主键ID')
    patient_id = db.Column(db.Integer, nullable=False, comment='患者ID')  # 关联患者表
    doctor_id = db.Column(db.Integer, nullable=False, comment='医生ID')  # 关联医生表
    browse_time = db.Column(db.DateTime, default=datetime.now, nullable=False, comment='浏览时间')  # 默认为当前时间
    browse_count = db.Column(db.Integer, default=1, nullable=False, comment='浏览次数')  # 默认为1

    def __repr__(self):
        return f'<UserBrowseHistory {self.patient_id}浏览{self.doctor_id}>'


# 根路径重定向（原有）
@app.route('/')
def index():
    return redirect(url_for('login_page'))


# 登录页面（原有）
@app.route('/login', methods=['GET'])
def login_page():
    return render_template('login.html')

# 医生登录处理（原有）

from flask import session, redirect, url_for, render_template


@app.route('/doctor/login', methods=['POST'])
def doctor_login():
    phone = request.form.get('identifier')  # 使用手机号作为账号
    email = request.form.get('password')  # 使用邮箱作为密码（仅示例）

    # 查询医生用户
    doctor = Doctor.query.filter_by(phone=phone).first()

    if doctor and doctor.email == email:  # 验证邮箱作为密码
        session['doctor_id'] = doctor.id
        session['doctor_name'] = doctor.name
        session['is_doctor'] = True

        return jsonify({
            "message": "医生登录成功",
            "status": 200,
            "redirect": url_for('doctor_center'),
            "doctor": {
                "name": doctor.name,
                "department": doctor.department.name if doctor.department else ""
            }
        })
    else:
        return jsonify({
            "message": "手机号或邮箱不正确",
            "status": 401
        }), 401


@app.route('/doctor/center')
def doctor_center():
    if 'doctor_id' not in session or not session.get('is_doctor'):
        return jsonify({
            "message": "请先以医生身份登录",
            "status": 401,
            "redirect": url_for('login')
        }), 401

    doctor = Doctor.query.get(session['doctor_id'])
    if not doctor:
        session.clear()
        return redirect(url_for('login'))

    # 获取当前医生的所有预约（按预约时间排序）
    appointments = Appointment.query.filter_by(doctor_id=doctor.id).order_by(Appointment.appointment_time.desc()).all()

    return render_template('doctor_center.html',
                           doctor=doctor,
                           appointments=appointments)
# 普通用户登录处理（原有）
@app.route('/login', methods=['POST'])
def login():
    identifier = request.form.get('identifier')
    password = request.form.get('password')
    if re.match(r'^1[3-9]\d{9}$', identifier):
        user = Patient.query.filter_by(phone=identifier).first()
    elif re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', identifier):
        user = Patient.query.filter_by(email=identifier).first()
    else:
        return jsonify({"message": "请输入有效的电话号码或电子邮箱", "status": 401})
    if user and check_password_hash(user.password, password):
        user.last_login_time = datetime.now()
        db.session.commit()
        session['patient_id'] = user.id
        session['is_admin'] = False
        session['username'] = user.username
        session['phone'] = user.phone
        return jsonify({"message": "登录成功", "status": 200, "is_admin": False})
    else:
        return jsonify({"message": "电话号码，邮箱或密码错误", "status": 401})



# 普通用户注册页面（原有）
@app.route('/register', methods=['GET'])
def register_page():
    return render_template('register.html')




# 普通用户注册处理（原有）
@app.route('/register', methods=['POST'])
def register():
    try:
        data = request.get_json()
        username = data.get('username')
        password = data.get('password')
        gender = data.get('gender')
        age = data.get('age')
        phone = data.get('phone')
        email = data.get('email')
        id_card = data.get('id_card')
        login_type = data.get('login_type', 0)
        medical_history = data.get('medical_history', '')
        if not username or not password or not phone or not email:
            return jsonify({"message": "注册信息不完整（用户名、密码、电话、邮箱为必填项）", "status": 400})
        if len(password) < 6:
            return jsonify({"message": "密码长度不能少于 6 位", "status": 400})
        if not re.match(r'^1[3-9]\d{9}$', phone):
            return jsonify({"message": "请输入正确的手机号格式", "status": 400})
        if not re.match(r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$', email):
            return jsonify({"message": "请输入正确的邮箱格式", "status": 400})
        if Patient.query.filter_by(phone=phone).first():
            return jsonify({"message": "该手机号已被注册", "status": 409})
        if Patient.query.filter_by(email=email).first():
            return jsonify({"message": "该邮箱已被注册", "status": 409})
        hashed_password = generate_password_hash(password, method='pbkdf2:sha256', salt_length=8)
        new_user = Patient(
            username=username,
            password=hashed_password,
            gender=gender,
            age=age,
            phone=phone,
            email=email,
            id_card=id_card,
            login_type=login_type,
            medical_history=medical_history,
            status=1,
            create_time=datetime.now(),
            update_time=datetime.now()
        )
        db.session.add(new_user)
        db.session.commit()
        return jsonify({"message": "注册成功", "status": 200})
    except Exception as e:
        db.session.rollback()
        return jsonify({"message": f"注册失败: {str(e)}", "status": 500})




# 患者帮助页面（原有）
@app.route('/help', methods=['GET'])
def help_page():
    return render_template('help.html')


@app.route('/department')
def department_index():
    all_departments = get_objects(Department)
    parent_departments = []  # 一级科室（parent_id为Null）
    child_departments = []  # 二级科室（parent_id不为Null）

    # 1. 分离一级和二级科室
    for dept in all_departments:
        if dept.parent_id is None:
            dept.children = []
            parent_departments.append(dept)
        else:

            child_departments.append(dept)

    # 2. 严格通过parent_id绑定二级科室到一级科室
    for child in child_departments:
        # 遍历所有一级科室，找到匹配的parent_id
        matched = False  # 标记是否找到匹配的一级科室
        for parent in parent_departments:
            if child.parent_id == parent.id:
                parent.children.append(child)
                matched = True
                break
        # 调试：若二级科室未找到对应一级科室，打印错误（方便排查数据问题）
        if not matched:
            print(f"警告：二级科室【{child.name}（id={child.id}）】的parent_id={child.parent_id}无效，未找到对应一级科室")

    # 调试：打印一级科室及其二级科室数量（确认数据是否正确）
    for p in parent_departments:
        print(f"一级科室：{p.name}（id={p.id}），二级科室数量：{len(p.children)}")

    return render_template('choose.html', parent_departments=parent_departments)

# 医生列表页（原有）
@app.route('/doctors')
def doctors_list():
    dept_id = request.args.get('dept_id', type=int)
    if not dept_id:
        return redirect(url_for('department_index'))
    department = get_object(Department, id=dept_id)
    doctors = get_objects(Doctor, department_id=dept_id) if department else []  # 当前选择科室的全部医生

    # 浏览记录逻辑（原有）
    if 'patient_id' in session:
        patient_id = session['patient_id']
        for doctor in doctors:
            existing_history = get_object(UserBrowseHistory, patient_id=patient_id, doctor_id=doctor.id)
            if existing_history:
                existing_history.browse_time = datetime.now()
                existing_history.browse_count += 1
            else:
                new_history = UserBrowseHistory(patient_id=patient_id, doctor_id=doctor.id)
                db.session.add(new_history)
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print(f"浏览记录提交失败：{str(e)}")

    return render_template('doctors.html', department=department, doctors=doctors)

# 搜索医生
# 讯飞参数
APPID = '3da8adca'
APIKey = '2b7571091761b0f4ab5c202fd9f5b822'
APISecret = 'YjgxZDE5NWM0ODVmNjRhMDRmODBjM2I1'

# 模拟医生数据
doctors = get_all_doctors()
# print(len(doctors))
# 读取department.txt 文件信息
def load_departments():
    dept_file = os.path.join(app.root_path, 'dict', 'department.txt')
    departments = []
    try:
        with open(dept_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    departments.append(line)
    except Exception as e:
        print(f"读取科室文件错误: {e}")
    return departments

# 查询医生

@app.route('/search', methods=['GET', 'POST'])
def search():
    # 获取查询参数
    if request.method == 'POST':
        query = request.form.get('query', '').strip()
        department = request.form.get('department', '').strip()
        rating = request.form.get('rating', '').strip()
        page = 1  # POST 默认跳转到第1页
    else:
        query = request.args.get('query', '').strip()
        department = request.args.get('department', '').strip()
        rating = request.args.get('rating', '').strip()
        page = request.args.get('page', 1, type=int)

    # 获取全部科室供筛选下拉用
    departments = load_departments()

    # 初始筛选结果为全部医生
    filtered_results = get_browsed_doctors(session.get('patient_id'))
    # print(filtered_results)
    # print(filtered_results)
    filtered_results1  = doctors
    # ---- 关键词搜索逻辑 ----
    if query:
        # 调用智能搜索方法，如果能匹配到智能结果
        intelligent_results = search_names(query)
        if intelligent_results:
            target_names = [doc['name'] for doc in doctors if doc['name'] in intelligent_results]
            filtered_results1 = [doc for doc in filtered_results1 if doc['name'] in target_names]
        else:
            # 否则使用普通模糊匹配（姓名 或 科室）
            q = query.lower()
            filtered_results1 = [
                doc for doc in filtered_results1
                if q in doc['name'].lower() or q in doc['speciality'].lower()
            ]
        if len(filtered_results1) == 0:
            filtered_results1 = doctors

    # ---- 科室筛选 ----
    if department:
        # filtered_results = [doc for doc in filtered_results if doc['department_id'] == department]
        filtered_results1 = [
            doc for doc in filtered_results1
            if Department.query.get(doc['department_id']).name == department
        ]
        if len(filtered_results1) == 0:
            filtered_results1 = doctors
    # ---- 评分筛选 ----
    if rating and rating.isdigit():
        min_rating = int(rating)
        filtered_results1 = [doc for doc in filtered_results1 if doc['rating'] >= min_rating]
        if len(filtered_results1) == 0:
            filtered_results1 = doctors

        
    if len(filtered_results1) != len(doctors):
        filtered_results = filtered_results1
    # ---- 分页处理 ----
    PER_PAGE = 6
    total_results = len(filtered_results)
    total_pages = (total_results + PER_PAGE - 1) // PER_PAGE  # 向上取整
    start_idx = (page - 1) * PER_PAGE
    end_idx = start_idx + PER_PAGE
    paginated_results = filtered_results[start_idx:end_idx]
    # print(paginated_results) # 测试
    # ---- 渲染 ----
    return render_template(
        'search.html',
        query=query,
        results=paginated_results,
        departments=departments,
        selected_department=department,
        selected_rating=rating,
        page=page,
        total_pages=total_pages
    )


@app.route('/doctor/<int:doctor_id>')
def doctor_detail(doctor_id):
    try:
        connection = get_db_connection()
        with connection.cursor() as cursor:
            sql = """
            SELECT d.id as doctor_id, d.name as doct_name, 
                   d.speciality as specialize, d.doctorIntro, d.keyworks, d.picture as pictures,
                   t.title as grade,
                   dep2.name as faculty_two_name,
                   dep1.name as faculty_one_name
            FROM doctor d
            LEFT JOIN title t ON d.title_id = t.id
            LEFT JOIN department dep2 ON d.department_id = dep2.id
            LEFT JOIN department dep1 ON dep2.parent_id = dep1.id
            WHERE d.id = %s
            """
            cursor.execute(sql, (doctor_id,))
            result = cursor.fetchone()

        if not result:
            return redirect(url_for('index'))

        doctor = pd.Series(result)

        # 提取关键词（从专长和简介两个字段）
        keyworks = nlp.extract_keyworks_from_all([
            doctor['specialize'],
            doctor['doctorIntro']
        ])

        # 如果没有提取到关键词，使用默认关键词
        if not keyworks:
            keyworks = doctor['keyworks'] or ""

        # 更新数据库中的关键词
        with connection.cursor() as update_cursor:
            update_sql = "UPDATE doctor SET keyworks = %s WHERE id = %s"
            update_cursor.execute(update_sql, (keyworks, doctor_id))
            connection.commit()

        # 构建医生信息字典
        doctor_info = {
            '姓名': doctor['doct_name'],
            '职位': doctor['grade'],
            '一级科室': doctor['faculty_one_name'],
            '二级科室': doctor['faculty_two_name'],
            '专攻方向': doctor['specialize'],
            '介绍': doctor['doctorIntro'],
            '关键词': keyworks,
            '照片': doctor['pictures']
        }

    except pymysql.Error as e:
        print(f"获取医生详情或更新关键词错误: {e}")
        connection.rollback()
        return redirect(url_for('index'))
    finally:
        if 'connection' in locals() and connection.open:
            connection.close()

    current_page = request.args.get('current_page', 1)
    return render_template('doctor_detail_test.html',
                           doctor_info=doctor_info,
                           current_page=current_page)
# 添加照片路由
@app.route('/photo/<int:doctor_id>')
def get_photo(doctor_id):
    try:
        connection = get_connection()
        with connection.cursor() as cursor:
            sql = "SELECT picture FROM doctor WHERE id = %s"
            cursor.execute(sql, (doctor_id,))
            result = cursor.fetchone()
        if result and result['picture']:
            return send_file(
                io.BytesIO(result['picture']),
                mimetype='image/jpeg'
            )
        else:
            return send_file('static/1.png')  # 准备一个默认图片
    except Exception as e:
        print(f"获取照片错误: {e}")
        return send_file('static/1.png')
    finally:
        if 'connection' in locals() and connection.open:
            connection.close()


# 评论
def load_data_from_db():
    try:
        connection = get_connection()
        with connection.cursor() as cursor:
            sql = """
            SELECT d.id AS doctor_id,
                   d.name AS doct_name,
                   d.department_id,
                   AVG(dr.rating) AS rating
            FROM doctor d
            LEFT JOIN doctor_review dr ON d.id = dr.doctor_id
            GROUP BY d.id, d.name, d.department_id
            """
            cursor.execute(sql)
            result = cursor.fetchall()
            df = pd.DataFrame(result)
            return df
    except pymysql.Error as e:
        print(f"数据库错误: {e}")
        return pd.DataFrame()
    finally:
        if 'connection' in locals() and connection.open:
            connection.close()

@app.route('/doctor/<int:doctor_id>/comments')
def doctor_comments(doctor_id):
    try:
        connection = get_connection()
        with connection.cursor() as cursor:
            # 联表查询评论及用户名
            sql = """
            SELECT dr.*, p.username AS user_name
            FROM doctor_review dr
            LEFT JOIN patient p ON dr.patient_id = p.id
            WHERE dr.doctor_id = %s
            ORDER BY dr.review_time DESC
            """
            cursor.execute(sql, (doctor_id,))
            reviews = cursor.fetchall()
            print(f"✅ doctor_id={doctor_id} 的评论数量: {len(reviews)}")
            for i, r in enumerate(reviews):
                print(f"第{i+1}条评论内容: {r.get('content', '无')}, 用户名: {r.get('user_name', '匿名')}")

            # 查医生信息
            cursor.execute("SELECT name, department_id FROM doctor WHERE id = %s", (doctor_id,))
            doctor_result = cursor.fetchone()
            # print("✅ doctor表查询结果:", doctor_result)

            if doctor_result:
                doctor_info = {
                    '姓名': doctor_result['name'],
                    '科室': doctor_result['department_id']
                }
            else:
                doctor_info = {
                    '姓名': '未知医生',
                    '科室': '未知科室'
                }

        total_reviews = len(reviews)
        current_page_str = request.args.get('current_page', '1')
        try:
            current_page = int(current_page_str)
        except ValueError:
            current_page = 1

    except pymysql.Error as e:
        # print(f"❌ 获取医生评论错误: {e}")
        reviews = []
        total_reviews = 0
        current_page = 1
        doctor_info = {
            '姓名': '数据库错误',
            '科室': '无'
        }
    finally:
        if 'connection' in locals() and connection.open:
            connection.close()

    # print(f"✅ 传入模板的医生信息: {doctor_info}")
    # print(f"✅ 当前页: {current_page}，总评论数: {total_reviews}")

    return render_template('doctor_comments.html',
                           doctor_id=doctor_id,
                           doctor_info=doctor_info,
                           reviews=reviews,
                           total_reviews=total_reviews,
                           current_page=current_page)

# 处理提交评论的路由
keyword_processor = KeywordProcessor()
sensitive_words = ["混蛋", "垃圾", "傻逼", "庸医", "去死", "妈的", "tmd"]
for word in sensitive_words:
    keyword_processor.add_keyword(word)
#插入评论
@app.route('/doctor/<int:doctor_id>/submit_comment', methods=['POST'])
def submit_comment(doctor_id):
    print(f"收到评论提交请求，doctor_id={doctor_id}")
    user_name = request.form.get('user_name')
    rating_str = request.form.get('rating')
    comments = request.form.get('comments')

    print(f"user_name={user_name}, rating={rating_str}, comments={comments}")

    # 检查评论中是否包含敏感词
    found_keywords = keyword_processor.extract_keywords(comments)
    if found_keywords:
        print(f"检测到敏感词: {found_keywords}")
        flash("检测到非法语句，请重新提交")
        return redirect(url_for('doctor_comments', doctor_id=doctor_id))  # 直接返回，不执行后续代码

    try:
        rating = float(rating_str)
    except (TypeError, ValueError):
        print("评分转换失败，默认评分为0")
        rating = 0

    sentiment = analyze_sentiment(comments)  # 分析情感
    print(f"分析出的情感: {sentiment}")

    # 用 session 获取 patient_id
    patient_id = session.get('patient_id')
    if not patient_id:
        print("未登录，无法获取 patient_id")
        return redirect(url_for('index'))

    try:
        connection = get_connection()
        with connection.cursor() as cursor:
            insert_sql = """INSERT INTO doctor_review (doctor_id, patient_id, department_id, rating, content, sentiment, review_time, create_time, update_time)
                            VALUES (%s, %s, %s, %s, %s, %s, NOW(), NOW(), NOW())"""
            cursor.execute(insert_sql, (doctor_id, patient_id, 1, rating, comments, sentiment))
        connection.commit()
        print("评论插入数据库成功")
    except pymysql.Error as e:
        print(f"插入评论到数据库时出错: {e}")
    finally:
        if 'connection' in locals() and connection.open:
            connection.close()

    return redirect(url_for('doctor_comments', doctor_id=doctor_id))

# 智能机器人回复
handler = ChatBotGraph()


@app.route('/chatbot', methods=['GET', 'POST'])
def chatbot():
    username = session.get('username')
    phone = session.get('phone')

    if not username or not phone:
        return redirect('/login')

    # print(username, phone) # 测试
    chat_history = []

    try:
        conn = get_connection()
        if request.method == 'POST':
            question = request.form.get('question')
            answer, from_api = handler.chat_main(question)

            # 插入聊天记录，字段改为 username
            with conn.cursor() as cursor:
                sql = "INSERT INTO chat_history (username, phone, question, answer, from_api) VALUES (%s, %s, %s, %s, %s)"
                cursor.execute(sql, (username, phone, question, answer, 1 if from_api else 0))
            conn.commit()

        # 查询时也改为按 username 查
        with conn.cursor() as cursor:
            sql = "SELECT question, answer, from_api, chat_time FROM chat_history WHERE username = %s ORDER BY chat_time ASC"
            cursor.execute(sql, (username,))
            chat_history = cursor.fetchall()

    except Exception as e:
        print(f"数据库操作错误: {e}")
    finally:
        if conn:
            conn.close()

    return render_template('Medical_Expert.html', chat_history=chat_history, realname=username)


@app.route('/upload_audio', methods=['POST'])
def upload_audio():
    audio_file = request.files.get('audio')
    if not audio_file:
        return jsonify({'error': 'No audio file uploaded'}), 400

    audio_bytes = audio_file.read()

    recognizer = SpeechRecognizer(APPID, APIKey, APISecret, audio_bytes)
    result_text = recognizer.recognize()

    return jsonify({'result': result_text})

# 预约表单页（原有）
@app.route('/appointment')
def appointment_form():
    doctor_id = request.args.get('doctor_id', type=int) #传递医生的id
    if not doctor_id:
        return redirect(url_for('department_index'))
    doctor = get_object(Doctor, id=doctor_id)
    if not doctor:
        return redirect(url_for('department_index'))
    department = get_object(Department, id=doctor.department_id)

    # 浏览记录逻辑（原有）
    if 'patient_id' in session:
        patient_id = session['patient_id']
        existing_history = get_object(UserBrowseHistory, patient_id=patient_id, doctor_id=doctor_id)
        if existing_history:
            existing_history.browse_time = datetime.now()
            existing_history.browse_count += 1
        else:
            new_history = UserBrowseHistory(patient_id=patient_id, doctor_id=doctor_id)
            db.session.add(new_history)
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            print(f"浏览记录提交失败：{str(e)}")

    return render_template('appointment.html', doctor=doctor, department=department)


# 处理预约提交（原有）
@app.route('/submit_appointment', methods=['POST'])
def submit_appointment():
    if 'patient_id' not in session:
        return "请先登录", 401
    try:
        form_data = request.form
        patient_id = session['patient_id']
        doctor_id = int(form_data['doctor_id'])
        department_id = int(form_data['department_id'])
        appointment_time_str = form_data['appointment_time']
        remark = form_data.get('remark', '')
        appointment_time = datetime.strptime(appointment_time_str, "%Y-%m-%dT%H:%M:%S")
        doctor = get_object(Doctor, id=doctor_id)
        if not doctor:
            return "医生信息不存在", 404
        appointment = Appointment(
            patient_id=patient_id,
            doctor_id=doctor_id,
            department_id=department_id,
            appointment_time=appointment_time,
            status=0,
            remark=remark,
            remind=0,
            meeting_number=doctor.meeting_number
        )
        db.session.add(appointment)
        db.session.flush()
        charge_record = ChargeRecord(
            appointment_id=appointment.id,
            fee=doctor.consultation_fee,
            payment_status=0
        )
        db.session. add(charge_record)
        db.session.commit()
        return redirect(url_for('success', appt_id=appointment.id))
    except Exception as e:
        db.session.rollback()
        return f"预约失败: {str(e)}", 500


# 预约成功页（原有）
@app.route('/success')
def success():
    appt_id = request.args.get('appt_id', type=int)
    appointment = get_object(Appointment, id=appt_id) if appt_id else None
    doctor_title = ""
    if appointment and appointment.doctor:
        doctor_title = appointment.doctor.title_id
    return render_template('success.html', appointment=appointment, doctor_title=doctor_title)


# 支付成功处理（原有）
@app.route('/payment_success')
def payment_success():
    appt_id = request.args.get('appt_id', type=int)
    appointment = get_object(Appointment, id=appt_id) if appt_id else None
    if appointment:
        charge_record = ChargeRecord.query.filter_by(appointment_id=appointment.id).first()
        if charge_record:
            charge_record.payment_status = 1
            db.session.commit()
    return redirect(url_for('success', appt_id=appt_id))


# 我的预约页面（原有）
@app.route('/my_appointments')
def my_appointments():
    if 'patient_id' not in session:
        return redirect(url_for('login_page'))
    patient_id = session['patient_id']
    from sqlalchemy.orm import joinedload
    appointments = Appointment.query.options(joinedload(Appointment.doctor)).filter_by(patient_id=patient_id).all()
    return render_template('my_appointments.html', appointments=appointments)


# 上下文处理器（原有）
@app.context_processor
def inject_functions():
    return dict(get_object=get_object)


# 注销（原有）
@app.route('/logout')
def logout():
    session.pop('patient_id', None)
    session.pop('admin_id', None)
    session.pop('is_admin', None)
    return redirect(url_for('login_page'))

# 用户中心

# 用户中心
@app.route('/user_center')
def user_center():
    patient_id = session.get('patient_id')
    if not patient_id:
        return redirect('/login')

    user = Patient.query.get(patient_id)
    if not user:
        return redirect('/login')

    # 查询智能机器人聊天记录
    chat_history = []
    try:
        conn = get_connection()
        with conn.cursor() as cursor:
            sql = "SELECT question, answer, from_api, chat_time FROM chat_history WHERE username = %s ORDER BY chat_time ASC"
            cursor.execute(sql, (user.username,))
            chat_history = cursor.fetchall()
    except Exception as e:
        print(f"数据库操作错误: {e}")
    finally:
        if conn:
            conn.close()

    # 查询预约记录（包含医生信息）
    from sqlalchemy.orm import joinedload
    appointments = Appointment.query.options(joinedload(Appointment.doctor))\
                        .filter_by(patient_id=patient_id).all()

    return render_template('user_center.html', user=user, chat_history=chat_history, appointments=appointments)

# 修改密码
@app.route('/change_password', methods=['POST'])
def change_password():
    patient_id = session.get('patient_id')
    if not patient_id:
        return jsonify({'success': False, 'message': '请先登录'}), 401

    user = Patient.query.get(patient_id)
    if not user:
        return jsonify({'success': False, 'message': '用户不存在'}), 404

    data = request.get_json()
    old_password = data.get('old_password')
    new_password = data.get('new_password')
    confirm_password = data.get('confirm_password')

    if not old_password or not new_password or not confirm_password:
        return jsonify({'success': False, 'message': '请填写完整的密码信息'})

    if not check_password_hash(user.password, old_password):
        return jsonify({'success': False, 'message': '原密码错误'})

    if new_password != confirm_password:
        return jsonify({'success': False, 'message': '两次新密码不一致'})

    user.password = generate_password_hash(new_password, method='pbkdf2:sha256', salt_length=8)
    db.session.commit()

    return jsonify({'success': True, 'message': '密码修改成功！'})

# 退出登录
@app.route('/user_logout')
def user_logout():
    session.clear()
    return redirect('/login')


#管理员页面


# 数据库连接配置
db_config = {
    'host': 'localhost',
    'user': 'root',
    'password': 'dumengtian463',
    'database': 'hospital8',
    'charset': 'utf8mb4',
    'cursorclass': pymysql.cursors.DictCursor
}


# 创建数据库连接
def get_db_connection():
    connection = pymysql.connect(**db_config)
    return connection


# 管理员登录装饰器
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'admin_logged_in' not in session:
            flash('请先登录管理员账号', 'danger')
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)

    return decorated_function


# 管理员登录
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        try:
            conn = get_db_connection()
            with conn.cursor() as cursor:
                cursor.execute("SELECT * FROM admin WHERE username = %s", (username,))
                admin = cursor.fetchone()

                if admin and admin['password'] == password:
                    session['admin_logged_in'] = True
                    session['admin_username'] = username
                    flash('登录成功', 'success')
                    return redirect(url_for('admin'))
                else:
                    flash('用户名或密码错误', 'danger')
        except Exception as e:
            print(f"数据库错误: {e}")
            flash('数据库错误，请稍后再试', 'danger')
        finally:
            conn.close()

    return render_template('admin_login.html')


# 管理员登出
@app.route('/admin/logout')
@admin_required
def admin_logout():
    session.pop('admin_logged_in', None)
    session.pop('admin_username', None)
    flash('您已成功登出', 'success')
    return redirect(url_for('admin_login'))


# 管理员主页
@app.route('/admin')
@admin_required
def admin():
    return render_template('admin.html')


# 首页


# 首页数据
@app.route('/home')
@admin_required
def home():
    shift_map = {0: '上午班', 1: '下午班', 2: '夜班'}
    status_map = {1: '已确认', 0: '待确认', 2: '调班申请中'}

    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # 获取今日预约数
            cursor.execute("SELECT COUNT(*) as count FROM appointment WHERE DATE(appointment_time) = CURDATE()")
            today_appointments = cursor.fetchone()['count']

            # 获取在线医生数（模拟数据）
            online_doctors = random.randint(40, 60)

            # 获取今日就诊数
            cursor.execute("""
                SELECT COUNT(*) as count FROM appointment 
                WHERE DATE(appointment_time) = CURDATE() AND status = 0
            """)
            today_visits = cursor.fetchone()['count']

            # 获取待处理提醒数
            cursor.execute("SELECT COUNT(*) as count FROM appointment WHERE remind = 1")
            pending_reminders = cursor.fetchone()['count']

            # 最近7天预约趋势
            cursor.execute("""
                           SELECT DATE(appointment_time) AS date, COUNT(*) AS count
                           FROM appointment
                           WHERE appointment_time >= CURDATE() - INTERVAL 6 DAY
                           GROUP BY DATE(appointment_time)
                           ORDER BY date
                       """)
            week_rows = cursor.fetchall()
            today_date = datetime.today().date()
            week_labels = [(today_date - timedelta(days=i)).strftime('%Y-%m-%d') for i in reversed(range(7))]
            week_map = {row['date'].strftime('%Y-%m-%d'): row['count'] for row in week_rows}
            week_data = [week_map.get(d, 0) for d in week_labels]

            # 最近30天预约趋势
            cursor.execute("""
                           SELECT DATE(appointment_time) AS date, COUNT(*) AS count
                           FROM appointment
                           WHERE appointment_time >= CURDATE() - INTERVAL 29 DAY
                           GROUP BY DATE(appointment_time)
                           ORDER BY date
                       """)
            month_rows = cursor.fetchall()
            month_labels = [(today_date - timedelta(days=i)).strftime('%Y-%m-%d') for i in reversed(range(30))]
            month_map = {row['date'].strftime('%Y-%m-%d'): row['count'] for row in month_rows}
            month_data = [month_map.get(d, 0) for d in month_labels]

            # 最近12个月预约趋势（年月）
            cursor.execute("""
                           SELECT DATE_FORMAT(appointment_time, '%Y-%m') AS month, COUNT(*) AS count
                           FROM appointment
                           WHERE appointment_time >= DATE_SUB(CURDATE(), INTERVAL 11 MONTH)
                           GROUP BY month
                           ORDER BY month
                       """)
            year_rows = cursor.fetchall()
            # 生成最近12个月年月标签
            year_labels = []
            current_month = today_date.replace(day=1)
            for i in reversed(range(12)):
                month_dt = (current_month - timedelta(days=30 * i))
                year_labels.append(month_dt.strftime('%Y-%m'))
            year_map = {row['month']: row['count'] for row in year_rows}
            year_data = [year_map.get(m, 0) for m in year_labels]

            cursor.execute("""
                SELECT a.id, p.username as patient_name, a.appointment_time, 
                       d.name as doctor_name, dept.name as department_name, a.status
                FROM appointment a
                JOIN patient p ON a.patient_id = p.id
                JOIN doctor d ON a.doctor_id = d.id
                JOIN department dept ON a.department_id = dept.id
                ORDER BY a.appointment_time DESC
                LIMIT 5
            """)
            recent_activities = cursor.fetchall()

            # --- 医生排班数据 ---
            cursor.execute("""
                            SELECT ds.doctor_id, ds.work_date, ds.shift, ds.status, 
                                   d.name as doctor_name, t.title, dept.name as department_name
                            FROM doctor_schedule ds
                            JOIN doctor d ON ds.doctor_id = d.id
                            JOIN title t ON d.title_id = t.id
                            JOIN department dept ON ds.department_id = dept.id
                            ORDER BY ds.work_date DESC, d.name
                            LIMIT 5
                        """)
            schedule_rows = cursor.fetchall()

            schedules = []
            for r in schedule_rows:
                schedules.append({
                    'doctor_name': r['doctor_name'],
                    'title': r['title'],
                    'department_name': r['department_name'],
                    'schedule_date': r['work_date'],
                    'shift': shift_map.get(r['shift'], '未知班次'),
                    'status': status_map.get(r['status'], '未知状态'),
                })
                # 构造卡片统计数据
                stats = [
                    {'name': '今日预约', 'value': today_appointments, 'change': 12.5, 'trend': 'up', 'color': 'green',
                     'icon': 'fa-user-injured'},
                    {'name': '在线医生', 'value': online_doctors, 'change': 5.7, 'trend': 'up', 'color': 'green',
                     'icon': 'fa-user-doctor'},
                    {'name': '今日就诊', 'value': today_visits, 'change': 3.2, 'trend': 'down', 'color': 'yellow',
                     'icon': 'fa-hospital-user'}
                ]

            return render_template('home.html',
                                   stats=stats,
                                   pending_reminders=pending_reminders,
                                   week_labels=week_labels,
                                   week_data=week_data,
                                   month_labels=month_labels,
                                   month_data=month_data,
                                   year_labels=year_labels,
                                   year_data=year_data,
                                   recent_activities=recent_activities,
                                   schedules=schedules)
    except Exception as e:
        print(f"数据库错误: {e}")
        stats = [
            {'name': '今日预约', 'value': 0, 'change': 0, 'trend': 'up', 'color': 'green', 'icon': 'fa-user-injured'},
            {'name': '在线医生', 'value': 0, 'change': 0, 'trend': 'up', 'color': 'green', 'icon': 'fa-user-doctor'},
            {'name': '今日就诊', 'value': 0, 'change': 0, 'trend': 'down', 'color': 'yellow',
             'icon': 'fa-hospital-user'},
        ]
        return render_template('home.html',
                               stats=stats,
                               pending_reminders=0,
                               week_labels=[], week_data=[],
                               month_labels=[], month_data=[],
                               year_labels=[], year_data=[],
                               recent_activities=[],
                               schedules=[])
    finally:
        conn.close()

#首页未来一周预测
@app.route('/api/future_appointments_predicted')
def future_appointments_predicted():
    conn = get_db_connection()
    cursor = conn.cursor()

    # 获取历史预约量（以今天为参照）
    cursor.execute("""
            SELECT DATE(appointment_time) AS ds, COUNT(*) AS y
            FROM appointment
            WHERE appointment_time < CURDATE()
            GROUP BY DATE(appointment_time)
            ORDER BY ds
        """)
    rows = cursor.fetchall()
    cursor.close()
    conn.close()

    if not rows:
        return jsonify({"labels": [], "data": []})

    # 转换为 Prophet 格式
    df = pd.DataFrame(rows)
    df['ds'] = pd.to_datetime(df['ds'])
    df['y'] = df['y'].astype(float)

    # 拟合 Prophet 模型
    model = Prophet(daily_seasonality=True)
    model.fit(df)

    # 预测从“今天”起的未来 7 天
    future = model.make_future_dataframe(periods=7)
    forecast = model.predict(future)

    # 取最后7天（即预测的部分）
    future_pred = forecast[['ds', 'yhat']].tail(7)
    future_pred['ds'] = future_pred['ds'].dt.strftime('%Y-%m-%d')

    return jsonify({
        'labels': future_pred['ds'].tolist(),
        'data': future_pred['yhat'].round().astype(int).tolist()
    })

# 预约提醒管理
@app.route('/appointment-reminder')
@admin_required
def appointment_reminder_page():
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # 获取需要提醒的预约
            cursor.execute("""
                SELECT a.id as order_id, p.username as patient_name, 
                       a.appointment_time, a.remind as reminder_status
                FROM appointment a
                JOIN patient p ON a.patient_id = p.id
                WHERE a.remind IN (0, 1) AND a.status = 0
                ORDER BY a.appointment_time
            """)
            reminders = cursor.fetchall()

            # 转换状态为文字描述
            for reminder in reminders:
                if reminder['reminder_status'] == 0:
                    reminder['reminder_status'] = '未提醒'
                elif reminder['reminder_status'] == 1:
                    reminder['reminder_status'] = '待发送'
                elif reminder['reminder_status'] == 2:
                    reminder['reminder_status'] = '已提醒'

            return render_template('appointment-reminder.html', reminders=reminders)
    except Exception as e:
        print(f"数据库错误: {e}")
        return render_template('appointment-reminder.html', reminders=[])
    finally:
        conn.close()


# 发送提醒API
@app.route('/api/send_reminder', methods=['POST'])
@admin_required
def send_reminder():
    order_id = request.form.get('order_id')
    if not order_id:
        return jsonify({'success': False, 'message': '缺少预约ID'})

    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # 更新提醒状态为已提醒
            cursor.execute("""
                UPDATE appointment SET remind = 2 
                WHERE id = %s AND status = 0
            """, (order_id,))
            conn.commit()

            if cursor.rowcount > 0:
                return jsonify({'success': True, 'message': '提醒发送成功'})
            else:
                return jsonify({'success': False, 'message': '预约不存在或已取消'})
    except Exception as e:
        print(f"数据库错误: {e}")
        return jsonify({'success': False, 'message': '发送提醒失败'})
    finally:
        conn.close()


# 挂号记录查询
@app.route('/registration_query')
@admin_required
def registration_query():
    return render_template('registration_query.html')

@app.route('/api/registration-data')
def registration_data_api():
    try:
        page = int(request.args.get('page', 1))
    except ValueError:
        page = 1
    try:
        size = int(request.args.get('size', 10))
    except ValueError:
        size = 10

    search = request.args.get('search', '').strip()

    data = get_registration_data(page, size, search)
    return jsonify(data)


# 挂号统计分析
@app.route('/registration-statistics')
@admin_required
def registration_statistics():
    return render_template('registration-statistics.html')

@app.route('/api/summary')
def api_summary():
    summary = get_summary_data()
    return jsonify(summary)

@app.route('/api/departments/statistics')
def api_departments_statistics():
    scope = request.args.get('scope', 'month')
    dist = get_department_distribution(scope)
    trend = get_registration_trend(scope)
    return jsonify({
        'department_distribution': dist,
        'registration_trend': trend
    })

@app.route('/api/details')
def api_details():
    scope = request.args.get('scope', 'month')
    details = get_registration_details()
    # get_registration_details 返回 {'month': [...], 'quarter': [...]}
    # 这里返回对应scope的数据
    return jsonify(details.get(scope, []))


# 医生资料管理
@app.route('/doctor-profile')
def doctor_profile():
    return render_template('doctor-profile.html')  # 渲染 HTML 页面

@app.route('/api/doctors')
@admin_required
def api_doctors():
    try:
        page = int(request.args.get('page', 1))
        page_size = int(request.args.get('pageSize', 5))
        keyword = request.args.get('keyword', '').strip()
        offset = (page - 1) * page_size

        conn = get_db_connection()
        with conn.cursor() as cursor:
            # 拼接搜索条件
            condition = ""
            params = []

            if keyword:
                condition += " AND (d.name LIKE %s OR t.title LIKE %s OR dept.name LIKE %s)"
                like_keyword = f"%{keyword}%"
                params += [like_keyword, like_keyword, like_keyword]

            # 查询总数
            count_sql = f"""
                SELECT COUNT(*) AS total
                FROM doctor d
                JOIN title t ON d.title_id = t.id
                JOIN department dept ON d.department_id = dept.id
                WHERE 1=1 {condition}
            """
            cursor.execute(count_sql, params)
            total = cursor.fetchone()['total']

            # 查询分页数据
            data_sql = f"""
                SELECT
                    CONCAT('D', LPAD(d.id, 3, '0')) AS id,
                    d.name,
                    t.title,
                    dept.name AS specialty,
                    d.department_id AS departmentId,
                    NULL AS subDepartmentId,
                    CONCAT(d.work_years, '年') AS experience,
                    d.doctorIntro AS description,
                    d.keyworks AS professionalTitle,
                    (
                        SELECT IF(COUNT(*) = 0, '未排班',
                            GROUP_CONCAT(
                                CONCAT(
                                    weekday_name, ' ',
                                    start_time, '-', end_time
                                )
                                ORDER BY weekday_order
                                SEPARATOR '，'
                            )
                        )
                        FROM (
                            SELECT
                                CASE WEEKDAY(s.work_date)
                                    WHEN 0 THEN '周一'
                                    WHEN 1 THEN '周二'
                                    WHEN 2 THEN '周三'
                                    WHEN 3 THEN '周四'
                                    WHEN 4 THEN '周五'
                                    WHEN 5 THEN '周六'
                                    WHEN 6 THEN '周日'
                                END AS weekday_name,
                                WEEKDAY(s.work_date) AS weekday_order,
                                MIN(CASE s.shift WHEN 0 THEN '08:00' WHEN 1 THEN '13:00' WHEN 2 THEN '18:00' END) AS start_time,
                                MAX(CASE s.shift WHEN 0 THEN '12:00' WHEN 1 THEN '17:00' WHEN 2 THEN '21:00' END) AS end_time
                            FROM doctor_schedule s
                            WHERE s.doctor_id = d.id
                                AND s.status = 1
                                AND YEARWEEK(s.work_date, 1) = YEARWEEK(CURDATE(), 1)
                            GROUP BY s.work_date
                        ) AS merged_schedule
                    ) AS schedule
                FROM doctor d
                JOIN title t ON d.title_id = t.id
                JOIN department dept ON d.department_id = dept.id
                WHERE 1=1 {condition}
                ORDER BY d.id
                LIMIT %s OFFSET %s
            """
            cursor.execute(data_sql, params + [page_size, offset])
            doctors = cursor.fetchall()

            return jsonify({
                "total": total,
                "page": page,
                "pageSize": page_size,
                "data": doctors
            })
    except Exception as e:
        print(f"数据库错误: {e}")
        return jsonify({"error": "服务器错误"}), 500
    finally:
        conn.close()

#编辑/添加医生部分：表单需要科室内容，从科室表中获取科室数据
@app.route('/api/departments/list')
@admin_required
def api_departments_list():
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("""
            SELECT id, name FROM department ORDER BY id ASC;
            """)
            departments = cursor.fetchall()
            return jsonify(departments)
    except Exception as e:
        print(f"数据库错误: {e}")
        return jsonify([])
    finally:
        conn.close()

#添加医生提交表单后需要在数据库中插入数据

@app.route('/api/doctors', methods=['POST'])
@admin_required
def add_doctor():
    try:
        data = request.get_json()
        print(data)
        name = data.get('name', '')
        title = data.get('title', '')
        department_id = data.get('department', '')
        specialty = data.get('specialty', '')
        work_years = int(data.get('experience', 0))  # ✅ 从前端获取从业年限
        doctorIntro = data.get('description', '')
        keyworks = data.get('professionalTitle', '')

        # 通过科室名称获取对应 department_id
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM department WHERE id = %s", (department_id,))
            dept_row = cursor.fetchone()
            if not dept_row:
                return jsonify({"error": "无效的科室名称"}), 400
            department_id = dept_row['id']

            # 获取默认 title_id（可根据需求动态获取）
            cursor.execute("SELECT id FROM title WHERE title = %s", (title,))
            title_row = cursor.fetchone()
            if not title_row:
                return jsonify({"error": "无效的职称"}), 400
            title_id = title_row['id']

            # 插入医生记录
            cursor.execute("""
                INSERT INTO doctor (name, title_id, department_id, work_years, doctorIntro, keyworks)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (name, title_id, department_id, work_years, doctorIntro, keyworks))
            conn.commit()
            return jsonify({"message": "医生添加成功"}), 201
    except Exception as e:
        print(f"添加医生失败: {e}")
        return jsonify({"error": "服务器错误"}), 500
    finally:
        conn.close()

#编辑医生，修改数据库中的数据
@app.route('/api/doctors', methods=['PUT'])
@admin_required
def update_doctor():
    try:
        data = request.get_json()

        doctor_id = data.get('id')
        name = data.get('name', '')
        title = data.get('title', '')
        department_name = data.get('specialty', '')
        work_years = int(data.get('experience', 0))
        doctorIntro = data.get('description', '')
        keyworks = data.get('professionalTitle', '')

        if not doctor_id:
            return jsonify({'error': '缺少医生ID'}), 400

        conn = get_db_connection()
        with conn.cursor() as cursor:
            # 查找 department_id
            cursor.execute("SELECT id FROM department WHERE name = %s", (department_name,))
            dept_row = cursor.fetchone()
            if not dept_row:
                return jsonify({'error': '无效的科室名称'}), 400
            department_id = dept_row['id']

            # 查找 title_id
            cursor.execute("SELECT id FROM title WHERE title = %s", (title,))
            title_row = cursor.fetchone()
            if not title_row:
                return jsonify({'error': '无效的职称'}), 400
            title_id = title_row['id']

            # 去掉D前缀（如 D001 → 1）
            real_id = int(doctor_id.replace('D', ''))

            # 更新医生记录
            cursor.execute("""
                UPDATE doctor
                SET name=%s, title_id=%s, department_id=%s, work_years=%s,
                    doctorIntro=%s, keyworks=%s
                WHERE id=%s
            """, (name, title_id, department_id, work_years, doctorIntro, keyworks, real_id))

            conn.commit()
            return jsonify({'message': '医生信息更新成功'}), 200
    except Exception as e:
        print(f"更新医生失败: {e}")
        return jsonify({'error': '服务器内部错误'}), 500
    finally:
        conn.close()

#删除医生信息
@app.route('/api/doctors/<doctor_id>', methods=['DELETE'])
@admin_required
def delete_doctor(doctor_id):
    # 需要把 doctor_id 中的 D 去掉，转换成数字id
    try:
        # 去掉开头的 'D'，转换为int
        real_id = int(doctor_id.lstrip('D'))
    except ValueError:
        return jsonify({"error": "医生ID格式错误"}), 400

    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("SELECT id FROM doctor WHERE id = %s", (real_id,))
            if cursor.fetchone() is None:
                return jsonify({"error": "医生不存在"}), 404

            cursor.execute("SELECT COUNT(*) AS cnt FROM appointment WHERE doctor_id = %s", (real_id,))
            count = cursor.fetchone()['cnt']
            if count > 0:
                return jsonify({"error": "该医生有未处理的预约，不能删除"}), 400

            cursor.execute("DELETE FROM doctor WHERE id = %s", (real_id,))
            conn.commit()
            return jsonify({"message": "医生删除成功"}), 200
    except Exception as e:
        print(f"删除医生失败: {e}")
        return jsonify({"error": "服务器错误"}), 500
    finally:
        conn.close()



# 医生服务评价
@app.route('/doctor-evaluation')
@admin_required
def doctor_evaluation():
        return render_template('doctor-evaluation.html')

@app.route('/api/reviews')
@admin_required
def api_reviews():
    try:
        page = int(request.args.get('page', 1))
        page_size = int(request.args.get('pageSize', 5))
        search = request.args.get('search', '').strip()
        print(f"接收到请求参数：page={page}, pageSize={page_size}, search='{search}'")  # 这里打印参数

        offset = (page - 1) * page_size
        conn = get_db_connection()
        with conn.cursor() as cursor:
            search_sql = ""
            search_args = []
            if search:
                search_sql = """
                    WHERE d.name LIKE %s OR p.username LIKE %s OR r.content LIKE %s
                """
                search_args = ['%' + search + '%'] * 3

            # 查询总数
            cursor.execute(f"""
                SELECT COUNT(*) AS total
                FROM doctor_review r
                JOIN doctor d ON r.doctor_id = d.id
                JOIN patient p ON r.patient_id = p.id
                {search_sql}
            """, search_args)
            total = cursor.fetchone()['total']

            # 查询数据，加入分页和搜索条件
            cursor.execute(f"""
                SELECT r.id, d.name AS doctor_name, p.username AS patient_name,
                       r.rating, r.content, r.review_time
                FROM doctor_review r
                JOIN doctor d ON r.doctor_id = d.id
                JOIN patient p ON r.patient_id = p.id
                {search_sql}
                ORDER BY r.review_time DESC
                LIMIT %s OFFSET %s
            """, search_args + [page_size, offset])
            reviews = cursor.fetchall()

            for r in reviews:
                if isinstance(r['review_time'], datetime):
                    r['review_time'] = r['review_time'].strftime('%Y-%m-%d %H:%M:%S')

            return jsonify({
                'total': total,
                'page': page,
                'pageSize': page_size,
                'data': reviews
            })
    except Exception as e:
        print(f"加载评价失败: {e}")
        return jsonify({'error': '加载失败'}), 500
    finally:
        conn.close()

#获取单条评价详情
@app.route('/api/doctor_reviews/<int:review_id>')
@admin_required
def get_review_detail(review_id):
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT r.id, d.name as doctor_name, p.username as patient_name,
                       r.rating, r.content, r.review_time
                FROM doctor_review r
                JOIN doctor d ON r.doctor_id = d.id
                JOIN patient p ON r.patient_id = p.id
                WHERE r.id = %s
            """, (review_id,))
            review = cursor.fetchone()
            if not review:
                return jsonify({"error": "未找到该评价"}), 404

            if isinstance(review['review_time'], datetime):
                review['review_time'] = review['review_time'].strftime('%Y-%m-%d %H:%M:%S')

            return jsonify(review)
    except Exception as e:
        print("获取评价详情失败：", e)
        return jsonify({"error": "服务器错误"}), 500
    finally:
        conn.close()



#删除患者评价
@app.route('/api/reviews/<int:review_id>', methods=['DELETE'])
@admin_required
def delete_review(review_id):
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM doctor_review WHERE id = %s", (review_id,))
            conn.commit()
            return jsonify({'message': '删除成功'}), 200
    except Exception as e:
        print(f"删除失败: {e}")
        return jsonify({'error': '服务器错误'}), 500
    finally:
        conn.close()


# 科室信息维护
@app.route('/department-info')
@admin_required
def department_info():
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT id, name, location, service_hours, description, parent_id
                FROM department
            """)
            departments = cursor.fetchall()

            # 拆解 description 字段为 dept_type 和 description 文本
            for dept in departments:
                if '|' in dept['description']:
                    dept['dept_type'], dept['description'] = dept['description'].split('|', 1)
                else:
                    dept['dept_type'] = dept['description']
                    dept['description'] = ''
                # 移除这句（它会覆盖真实parent_id）
                # dept['dept_id'] = "一级科室"

        return render_template('department-info.html', departments=departments)
    except Exception as e:
        print(f"数据库错误: {e}")
        return render_template('department-info.html', departments=[])
    finally:
        conn.close()

from flask import request, jsonify


from datetime import datetime

@app.route('/api/departments', methods=['POST'])
@admin_required
def create_department():
    data = request.get_json()
    name = data.get('name')
    location = data.get('location')
    parent_id = data.get('parent_id')  # 可以为 None

    if not name or not location:
        return jsonify({'success': False, 'message': '科室名称和位置不能为空'})

    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            sql = """
                INSERT INTO department (name, location, parent_id, create_time, update_time)
                VALUES (%s, %s, %s, %s, %s)
            """
            cursor.execute(sql, (name, location, parent_id, now, now))
            conn.commit()

            # 获取新插入的 id
            new_id = cursor.lastrowid
            return jsonify({
                'success': True,
                'message': '新增成功',
                'department': {
                    'id': new_id,
                    'name': name,
                    'location': location,
                    'parent_id': parent_id
                }
            })
    except Exception as e:
        print("新增科室失败：", e)
        return jsonify({'success': False, 'message': str(e)})
    finally:
        conn.close()

@app.route('/api/departments', methods=['POST'])
@admin_required
def api_add_department():
    data = request.get_json()
    name = data.get('name')
    location = data.get('location')
    parent_id = data.get('parent_id', None)

    if not name or not location:
        return jsonify({'success': False, 'message': '科室名称和位置不能为空'})

    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO department (name, location, parent_id)
                VALUES (%s, %s, %s)
            """, (name, location, parent_id))
            conn.commit()
            new_id = cursor.lastrowid

        new_dept = {
            'id': new_id,
            'name': name,
            'location': location,
            'parent_id': parent_id
        }
        return jsonify({'success': True, 'department': new_dept})

    except Exception as e:
        print(f"新增科室失败: {e}")
        return jsonify({'success': False, 'message': str(e)})

    finally:
        conn.close()



@app.route('/api/departments/<int:dept_id>', methods=['PUT'])
@admin_required
def update_department(dept_id):
    """更新科室信息（包括名称、位置、类型等）"""
    data = request.json
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            # 查询当前 description
            cursor.execute("SELECT description FROM department WHERE id = %s", (dept_id,))
            result = cursor.fetchone()
            if not result:
                return jsonify({"success": False, "message": "科室不存在"}), 404

            current_desc = result['description']
            updates = []
            values = []

            # 更新科室类型（写入 description）
            if 'dept_type' in data:
                if '|' in current_desc:
                    new_desc = f"{data['dept_type']}|{current_desc.split('|', 1)[1]}"
                else:
                    new_desc = data['dept_type']
                updates.append("description = %s")
                values.append(new_desc)

            # 其他字段更新
            if 'name' in data:
                updates.append("name = %s")
                values.append(data['name'])
            if 'location' in data:
                updates.append("location = %s")
                values.append(data['location'])
            if 'service_hours' in data:
                updates.append("service_hours = %s")
                values.append(data['service_hours'])
            if 'parent_id' in data:
                updates.append("parent_id = %s")
                values.append(data['parent_id'])

            if not updates:
                return jsonify({"success": False, "message": "没有需要更新的数据"}), 400

            # 最后添加 WHERE 条件的参数
            values.append(dept_id)
            query = f"UPDATE department SET {', '.join(updates)} WHERE id = %s"

            print("执行SQL：", query)
            print("参数：", values)

            cursor.execute(query, values)
            conn.commit()

            return jsonify({"success": True, "message": "更新成功"})
    except Exception as e:
        print(f"数据库错误: {e}")
        return jsonify({"success": False, "message": "更新失败"}), 500
    finally:
        conn.close()


@app.route('/api/departments/<int:dept_id>', methods=['DELETE'])
@admin_required
def delete_department(dept_id):
    """删除科室"""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("DELETE FROM department WHERE id = %s", (dept_id,))
            conn.commit()
            return jsonify({"success": True, "message": "删除成功"})
    except Exception as e:
        print(f"数据库错误: {e}")
        return jsonify({"success": False, "message": "删除失败"}), 500
    finally:
        conn.close()



# 其他页面路由
# @app.route('/registration-cancellation')
# @admin_required
# def registration_cancellation():
#     return render_template('registration-cancellation.html')

# 1
@app.route('/doctor-sc')
@admin_required
def doctor_sc():
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # 获取医生排班数据
            cursor.execute("""
                SELECT 
                    ds.id,
                    d.name AS doctor_name,
                    dept.name AS department_name,
                    ds.schedule_date,
                    ds.start_time,
                    ds.end_time,
                    ds.available_slots
                FROM doctor_schedule ds
                JOIN doctor d ON ds.doctor_id = d.id
                JOIN department dept ON d.department_id = dept.id
                ORDER BY ds.schedule_date, ds.start_time
            """)
            schedules = cursor.fetchall()

        return render_template('doctor-sc.html', schedules=schedules)

    except Exception as e:
        traceback.print_exc()
        return f"获取排班数据错误: {e}"
    finally:
        if conn and conn.open:
            conn.close()

@app.route('/department-performance')
@admin_required
def department_performance():
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT DISTINCT 
                    CONCAT(YEAR(appointment_time), 'Q', QUARTER(appointment_time)) as period
                FROM appointment
                ORDER BY period DESC
            """)
            periods = [{"value": row['period'], "label": f"{row['period']}季度"} for row in cursor.fetchall()]

            if not periods:
                return render_template('department-performance.html', periods=[], current_period=None,
                                       efficiencyData=None, ratingData=None, performanceData=None, doctors=[], departmentData=None)

            current_period = periods[0]["value"]
            current_start, current_end = quarter_to_date_range(current_period)
            last_quarter = get_last_quarter(current_period)
            last_start, last_end = quarter_to_date_range(last_quarter)

            efficiency_data = calculate_efficiency(cursor, current_start, current_end, last_start, last_end)
            rating_data = calculate_rating(cursor, current_start, current_end, last_start, last_end)
            performance_data = calculate_dept_performance(cursor, current_start, current_end)
            doctors = get_best_doctors(cursor, current_start, current_end)

            # 新增调用 calculate_dept_comparison
            department_data = calculate_dept_comparison(cursor, current_start, current_end)

            return render_template('department-performance.html',
                                   periods=periods,
                                   current_period=current_period,
                                   efficiencyData=efficiency_data,
                                   ratingData=rating_data,
                                   performanceData=performance_data,
                                   doctors=doctors,
                                   departmentData=department_data)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"获取排班数据错误: {e}"
    finally:
        if conn and conn.open:
            conn.close()


def quarter_to_date_range(quarter_str):
    """将季度字符串转换为标准格式字符串日期"""
    year = int(quarter_str[:4])
    quarter = int(quarter_str[5])
    start_month = (quarter - 1) * 3 + 1
    end_month = start_month + 2
    start_date = datetime(year, start_month, 1).strftime('%Y-%m-%d')
    if end_month in [4, 6, 9, 11]:
        end_day = 30
    elif end_month == 2:
        end_day = 29 if (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)) else 28
    else:
        end_day = 31
    end_date = datetime(year, end_month, end_day).strftime('%Y-%m-%d')
    return start_date, end_date


def get_last_quarter(quarter_str):
    year = int(quarter_str[:4])
    quarter = int(quarter_str[5])
    return f"{year - 1}Q4" if quarter == 1 else f"{year}Q{quarter - 1}"

def get_latest_quarters(n=3):
    from datetime import date
    today = date.today()
    year = today.year
    quarter = (today.month - 1) // 3 + 1

    quarters = []
    for _ in range(n):
        quarters.append(f"{year}Q{quarter}")
        quarter -= 1
        if quarter == 0:
            quarter = 4
            year -= 1
    return quarters


def calculate_efficiency(cursor, current_start, current_end, last_start, last_end):
    cursor.execute("""
        SELECT 
            COUNT(CASE WHEN status = 3 THEN 1 END) AS completed,
            COUNT(*) AS total
        FROM appointment
        WHERE appointment_time BETWEEN %s AND %s
    """, (current_start, current_end))
    current = cursor.fetchone()
    current_efficiency = (current['completed'] / current['total'] * 100) if current and current['total'] else 0

    cursor.execute("""
        SELECT 
            COUNT(CASE WHEN status = 3 THEN 1 END) AS completed,
            COUNT(*) AS total
        FROM appointment
        WHERE appointment_time BETWEEN %s AND %s
    """, (last_start, last_end))
    last = cursor.fetchone()
    last_efficiency = (last['completed'] / last['total'] * 100) if last and last['total'] else 0

    return {
        "labels": ['本季度', '上季度'],
        "datasets": [{
            "label": '诊疗完成率(%)',
            "data": [round(current_efficiency, 1), round(last_efficiency, 1)],
            "backgroundColor": ['rgba(54, 162, 235, 0.7)', 'rgba(153, 102, 255, 0.7)'],
            "borderColor": ['rgb(54, 162, 235)', 'rgb(153, 102, 255)'],
            "borderWidth": 1
        }]
    }

def calculate_rating(cursor, current_start, current_end, last_start, last_end):
    cursor.execute("""
        SELECT AVG(r.rating) AS avg_rating
        FROM doctor_review r
        JOIN appointment a ON r.doctor_id = a.doctor_id
        WHERE a.appointment_time BETWEEN %s AND %s
    """, (current_start, current_end))
    current = cursor.fetchone()
    current_rating = round(current['avg_rating'], 1) if current and current['avg_rating'] is not None else 0

    cursor.execute("""
        SELECT AVG(r.rating) AS avg_rating
        FROM doctor_review r
        JOIN appointment a ON r.doctor_id = a.doctor_id
        WHERE a.appointment_time BETWEEN %s AND %s
    """, (last_start, last_end))
    last = cursor.fetchone()
    last_rating = round(last['avg_rating'], 1) if last and last['avg_rating'] is not None else 0

    return {
        "labels": ['本季度', '上季度'],
        "datasets": [{
            "label": '综合评分(1-5分)',
            "data": [current_rating, last_rating],
            "backgroundColor": ['rgba(255, 99, 132, 0.7)', 'rgba(54, 162, 235, 0.7)'],
            "borderColor": ['rgb(255, 99, 132)', 'rgb(54, 162, 235)'],
            "borderWidth": 1
        }]
    }

def calculate_dept_performance(cursor, start_date, end_date):
    cursor.execute("SELECT id, name FROM department")
    departments = cursor.fetchall()
    dept_names = []
    performance_scores = []

    for dept in departments:
        cursor.execute("""
            SELECT AVG(performance_score) as avg_performance
            FROM department_performance
            WHERE department_id = %s
              AND date_time BETWEEN %s AND %s
        """, (dept['id'], start_date, end_date))
        result = cursor.fetchone()
        score = round(result['avg_performance'], 2) if result and result['avg_performance'] is not None else 0
        dept_names.append(dept['name'])
        performance_scores.append(score)

    return {
        "labels": dept_names,
        "datasets": [{
            "label": '综合绩效分',
            "data": performance_scores,
            "backgroundColor": 'rgba(16, 185, 129, 0.7)',
            "borderColor": 'rgba(16, 185, 129, 1)',
            "borderWidth": 1
        }]
    }

def calculate_dept_comparison(cursor, start_date, end_date):
    cursor.execute("SELECT id, name FROM department")
    departments = cursor.fetchall()
    dept_names, treatment_counts, avg_ratings = [], [], []

    for dept in departments:
        # 诊疗数统计
        cursor.execute("""
            SELECT COUNT(*) AS count
            FROM appointment
            WHERE department_id = %s AND status = 3 AND appointment_time BETWEEN %s AND %s
        """, (dept['id'], start_date, end_date))
        count_result = cursor.fetchone()
        count = count_result['count'] if count_result and count_result['count'] is not None else 0

        # 平均评分统计
        cursor.execute("""
            SELECT AVG(r.rating) AS avg_rating
            FROM doctor_review r
            JOIN appointment a ON r.doctor_id = a.doctor_id
            WHERE a.department_id = %s AND a.appointment_time BETWEEN %s AND %s
        """, (dept['id'], start_date, end_date))
        rating_result = cursor.fetchone()
        avg_rating = rating_result['avg_rating'] if rating_result and rating_result['avg_rating'] is not None else 0

        dept_names.append(dept['name'])
        treatment_counts.append(count)
        avg_ratings.append(round(avg_rating, 1))

    # 返回格式和模板里期望的相匹配
    return {
        "labels": dept_names,
        "datasets": [
            {
                "label": "诊疗数",
                "data": treatment_counts,
                "backgroundColor": "rgba(54, 162, 235, 0.7)",
                "borderColor": "rgb(54, 162, 235)",
                "borderWidth": 1,
                "yAxisID": "y"
            },
            {
                "label": "平均评分",
                "data": avg_ratings,
                "backgroundColor": "rgba(255, 99, 132, 0.7)",
                "borderColor": "rgb(255, 99, 132)",
                "borderWidth": 1,
                "yAxisID": "y1"
            }
        ]
    }


def get_best_doctors(cursor, start_date, end_date):
    cursor.execute("""
        SELECT 
            d.id,
            d.name AS doctor_name,
            dept.name AS department_name,
            AVG(r.rating) AS avg_rating,
            COUNT(r.id) AS review_count,
            -- 诊疗数统计（本季度完成的预约）
            COALESCE((
                SELECT COUNT(*) 
                FROM appointment a2 
                WHERE a2.doctor_id = d.id AND a2.status = 3 
                  AND a2.appointment_time BETWEEN %s AND %s
            ), 0) AS treatment_count,
            -- 效率评分 = 完成预约数 / 总预约数 * 100
            COALESCE((
                SELECT ROUND(
                    CASE WHEN COUNT(*) = 0 THEN 0
                    ELSE COUNT(CASE WHEN status = 3 THEN 1 END) / COUNT(*) * 100 END, 1)
                FROM appointment a3 
                WHERE a3.doctor_id = d.id AND a3.appointment_time BETWEEN %s AND %s
            ), 0) AS efficiency_rating
        FROM doctor_review r
        JOIN doctor d ON r.doctor_id = d.id
        JOIN department dept ON d.department_id = dept.id
        JOIN appointment a ON r.doctor_id = a.doctor_id
        WHERE a.appointment_time BETWEEN %s AND %s
        GROUP BY d.id, dept.name
        ORDER BY avg_rating DESC, review_count DESC
        LIMIT 5
    """, (start_date, end_date, start_date, end_date, start_date, end_date))

    return cursor.fetchall()


# @app.route('/department-doctor')
# @admin_required
# def department_doctor():
#     return render_template('department-doctor.html')

@app.route('/department-performance-data')
@admin_required
def department_performance_data():
    period = request.args.get('period')  # 例如 "2025Q2"
    chart_type = request.args.get('type', 'treatment')  # 默认'treatment'

    if not period:
        return jsonify({"error": "缺少参数period"}), 400

    # 将季度字符串转为开始和结束日期
    start_date, end_date = quarter_to_date_range(period)

    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            # 根据 type 返回不同数据
            if chart_type == 'treatment':
                # 返回诊疗数数据
                data = calculate_dept_comparison(cursor, start_date, end_date)
                # 这里只返回诊疗数的部分，为前端切换时方便
                data = {
                    "labels": data["labels"],
                    "datasets": [data["datasets"][0]]  # 诊疗数
                }
            elif chart_type == 'rating':
                data = calculate_dept_comparison(cursor, start_date, end_date)
                # 这里只返回评分部分
                data = {
                    "labels": data["labels"],
                    "datasets": [data["datasets"][1]]  # 评分
                }
            else:
                # 默认返回全部或者空数据
                data = {"labels": [], "datasets": []}

        return jsonify(data)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500
    finally:
        if conn and conn.open:
            conn.close()


# 其他页面路由
@app.route('/registration-cancellation')
@admin_required
def registration_cancellation():
    return render_template('registration-cancellation.html')


# 通用查询方法
def query_db(query, args=None, fetchall=False):
    connection = get_db_connection()
    try:
        with connection.cursor() as cursor:
            cursor.execute(query, args or ())
            if fetchall:
                result = cursor.fetchall()
            else:
                result = cursor.fetchone()
        connection.commit()
        return result
    except Exception as e:
        connection.rollback()
        raise e
    finally:
        connection.close()

# 医生排班
@app.route('/doctor-scheduling')
@admin_required
def doctor_scheduling():
    try:
        # 获取筛选参数
        doctor_id = request.args.get('doctor_id')
        department_id = request.args.get('department_id')
        shift = request.args.get('shift')
        date = request.args.get('date')
        search = request.args.get('search')

        # 基础查询
        query = """
        SELECT ds.*, d.name AS doctor_name, dept.name AS department_name
        FROM doctor_schedule ds
        JOIN doctor d ON ds.doctor_id = d.id
        JOIN department dept ON ds.department_id = dept.id
        """
        conditions = []
        params = []
        # 构建筛选条件
        if doctor_id:
            conditions.append("ds.doctor_id = %s")
            params.append(doctor_id)
        if department_id:
            conditions.append("ds.department_id = %s")
            params.append(department_id)
        if shift:
            conditions.append("ds.shift = %s")
            params.append(shift)
        if date:
            conditions.append("ds.work_date = %s")
            params.append(date)
        if search:
            conditions.append("(d.name LIKE %s OR dept.name LIKE %s)")
            params.extend([f"%{search}%", f"%{search}%"])

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        query += " ORDER BY ds.work_date DESC, ds.shift"

        # 执行查询
        schedules = query_db(query, params, fetchall=True) or []

        # 获取所有医生和科室
        doctors = query_db("SELECT id, name, department_id FROM doctor ORDER BY name", fetchall=True) or []
        departments = query_db("SELECT id, name FROM department ORDER BY name", fetchall=True) or []

        # 统计数据
        today = datetime.now().strftime('%Y-%m-%d')
        stats = {
            'doctor_count': query_db("SELECT COUNT(*) AS count FROM doctor")['count'],
            'today_schedules': query_db(
                "SELECT COUNT(*) AS count FROM doctor_schedule WHERE work_date = %s",
                [today]
            )['count'],
            'pending_schedules': query_db(
                "SELECT COUNT(*) AS count FROM doctor_schedule WHERE status = 0"
            )['count']
        }

        # 班次映射
        shift_names = {0: '上午班', 1: '下午班', 2: '晚上班'}

        return render_template('doctor-scheduling.html',
                               doctors=doctors,
                               departments=departments,
                               schedules=schedules,
                               stats=stats,
                               shift_names=shift_names,
                               request_args=request.args)

    except Exception as e:
        app.logger.error(f"页面加载失败: {str(e)}")
        return render_template('error.html', message="数据加载失败"), 500

# 获取医生详情
@app.route('/api/doctors/<int:doctor_id>')
@admin_required
def get_doctor(doctor_id):
    try:
        doctor = query_db(
            "SELECT id, name, department_id FROM doctor WHERE id = %s",
            [doctor_id]
        )
        if not doctor:
            return jsonify({'error': '医生不存在'}), 404
        return jsonify(doctor)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

import logging
#添加排班
@app.route('/api/schedules', methods=['POST'])
@admin_required
def add_schedule():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': '请求体必须为JSON格式'}), 400

        # 验证必填字段
        required_fields = ['doctor_id', 'department_id', 'work_date', 'shift']
        for field in required_fields:
            if field not in data or data[field] in (None, ""):
                return jsonify({'error': f'缺少必要字段: {field}'}), 400

        # 验证日期格式
        try:
            datetime.strptime(data['work_date'], '%Y-%m-%d')
        except ValueError:
            return jsonify({'error': '日期格式必须为YYYY-MM-DD'}), 400

        # 验证班次值
        try:
            shift = int(data['shift'])
            if shift not in (0, 1, 2):
                return jsonify({'error': '班次必须为 0(上午)、1(下午) 或 2(晚上)'}), 400
        except (ValueError, TypeError):
            return jsonify({'error': '班次必须是整数'}), 400

        # 验证医生是否存在
        doctor = query_db("SELECT id FROM doctor WHERE id = %s", [data['doctor_id']])
        if not doctor:
            return jsonify({'error': '医生不存在'}), 404

        # 验证科室是否存在
        department = query_db("SELECT id FROM department WHERE id = %s", [data['department_id']])
        if not department:
            return jsonify({'error': '科室不存在'}), 404

        # 检查是否已存在相同排班
        existing = query_db("""
            SELECT id FROM doctor_schedule 
            WHERE doctor_id = %s AND work_date = %s AND shift = %s
        """, (data['doctor_id'], data['work_date'], shift))
        if existing:
            return jsonify({'error': '该医生此时段已有排班'}), 400

        # 插入排班
        connection = get_db_connection()
        with connection.cursor() as cursor:
            sql = """
            INSERT INTO doctor_schedule 
            (doctor_id, department_id, work_date, shift, available_slots, used_slots, create_time, update_time, status)
            VALUES (%s, %s, %s, %s, %s, %s, NOW(), NOW(), %s)
            """
            cursor.execute(sql, (
                data['doctor_id'],
                data['department_id'],
                data['work_date'],
                shift,
                20,  # available_slots
                0,  # used_slots
                1  # status
            ))
            connection.commit()
            # 记录成功日志
            #logging.info(f"Schedule created: doctor_id={data['doctor_id']}, date={data['work_date']}, shift={shift}")

            return jsonify({
                'message': '排班添加成功',
                'id': cursor.lastrowid,
                'doctor_id': data['doctor_id'],
                'work_date': data['work_date'],
                'shift': shift
            }), 201

    except pymysql.Error as e:
        logging.error(f"Database error: {str(e)}")
        return jsonify({'error': '数据库操作失败'}), 500
    except Exception as e:
        logging.error(f"Unexpected error: {str(e)}")
        return jsonify({'error': '服务器内部错误'}), 500
    finally:
        if 'connection' in locals():
            connection.close()

# 获取单条排班
@app.route('/api/schedules/<int:schedule_id>')
@admin_required
def get_schedule(schedule_id):
    try:
        schedule = query_db("""
            SELECT ds.*, d.name AS doctor_name, dept.name AS department_name
            FROM doctor_schedule ds
            JOIN doctor d ON ds.doctor_id = d.id
            JOIN department dept ON ds.department_id = dept.id
            WHERE ds.id = %s
        """, [schedule_id])

        if not schedule:
            return jsonify({'error': '排班不存在'}), 404

        # 格式化日期
        schedule['work_date'] = schedule['work_date'].strftime('%Y-%m-%d')
        return jsonify(schedule)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# 更新排班
@app.route('/api/schedules/<int:schedule_id>', methods=['PUT'])
@admin_required
def update_schedule(schedule_id):
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': '请求体必须为JSON格式'}), 400

        # 验证必填字段
        required_fields = ['doctor_id', 'department_id', 'work_date', 'shift', 'status']
        for field in required_fields:
            if field not in data or data[field] in (None, ""):
                return jsonify({'error': f'缺少必要字段: {field}'}), 400

        # 验证日期格式
        try:
            datetime.strptime(data['work_date'], '%Y-%m-%d')
        except ValueError:
            return jsonify({'error': '日期格式必须为YYYY-MM-DD'}), 400

        # 验证排班是否存在
        schedule = query_db("SELECT id FROM doctor_schedule WHERE id = %s", [schedule_id])
        if not schedule:
            return jsonify({'error': '排班不存在'}), 404

        # 验证医生是否存在
        doctor = query_db("SELECT id FROM doctor WHERE id = %s", [data['doctor_id']])
        if not doctor:
            return jsonify({'error': '医生不存在'}), 404

        # 验证科室是否存在
        department = query_db("SELECT id FROM department WHERE id = %s", [data['department_id']])
        if not department:
            return jsonify({'error': '科室不存在'}), 404

        # 更新排班
        connection = get_db_connection()
        with connection.cursor() as cursor:
            sql = """
            UPDATE doctor_schedule 
            SET doctor_id = %s,
                department_id = %s,
                work_date = %s,
                shift = %s,
                status = %s,
                update_time = NOW()
            WHERE id = %s
            """
            cursor.execute(sql, (
                data['doctor_id'],
                data['department_id'],
                data['work_date'],
                int(data['shift']),
                int(data['status']),
                schedule_id
            ))
            connection.commit()
            return jsonify({'message': '排班更新成功'})

    except pymysql.Error as e:
        return jsonify({'error': f'数据库错误: {e}'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if 'connection' in locals():
            connection.close()

# 删除排班
@app.route('/api/schedules/<int:schedule_id>', methods=['DELETE'])
@admin_required
def delete_schedule(schedule_id):
    try:
        # 验证排班是否存在
        schedule = query_db("SELECT id FROM doctor_schedule WHERE id = %s", [schedule_id])
        if not schedule:
            return jsonify({'error': '排班不存在'}), 404

        # 执行删除
        query_db("DELETE FROM doctor_schedule WHERE id = %s", [schedule_id])
        return jsonify({'message': '排班删除成功'})

    except pymysql.Error as e:
        return jsonify({'error': f'数据库错误: {e}'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# 获取统计数据
@app.route('/api/stats')
@admin_required
def get_stats():
    try:
        today = datetime.now().strftime('%Y-%m-%d')
        stats = {
            'doctor_count': query_db("SELECT COUNT(*) AS count FROM doctor")['count'],
            'today_schedules': query_db(
                "SELECT COUNT(*) AS count FROM doctor_schedule WHERE work_date = %s",
                [today]
            )['count'],
            'pending_schedules': query_db(
                "SELECT COUNT(*) AS count FROM doctor_schedule WHERE status = 0"
            )['count']
        }
        return jsonify(stats)
    except Exception as e:
        return jsonify({'error': str(e)}), 500






@app.route('/article-publishing')
@admin_required
def article_publishing():
    return render_template('article-publishing.html')


@app.route('/multimedia-management')
@admin_required
def multimedia_management():
    return render_template('multimedia-management.html')


@app.route('/language-support')
@admin_required
def language_support():
    return render_template('language-support.html')


@app.route('/comment-moderation')
@admin_required
def comment_moderation():
    return render_template('comment-moderation.html')

@app.route('/admin_logout2')
def admin_logout2():
    session.clear()  # 清除所有会话数据
    return redirect(url_for('admin_login'))
# 初始化数据库




# 应用启动（原有）
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        if not Admin.query.first():
            admin_password = generate_password_hash('admin123456', method='pbkdf2:sha256', salt_length=10)
            admin = Admin(username='doctor', password=admin_password)
            db.session.add(admin)
            db.session.commit()
            print("初始化成功，默认医生账号: doctor / admin123456")
    app.run(debug=True,host = '0.0.0.0',port=5057)