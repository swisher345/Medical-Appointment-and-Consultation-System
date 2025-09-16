import pymysql
from pymysql.cursors import DictCursor

# 数据库配置
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': 'dumengtian463',
    'database': 'hospital1',
    'charset': 'utf8mb4',
    'cursorclass': DictCursor
}

# 获取数据库连接
def get_db_connection():
    return pymysql.connect(**DB_CONFIG)

# 获取挂号数据（支持分页与搜索）
def get_registration_data(page=1, size=10, search=''):
    offset = (page - 1) * size
    conn = get_db_connection()

    try:
        with conn.cursor() as cursor:
            # 今日挂号数
            cursor.execute("SELECT COUNT(*) AS count FROM appointment WHERE DATE(appointment_time) = CURDATE()")
            today_appointments = cursor.fetchone()['count']

            # 今日就诊数
            cursor.execute("SELECT COUNT(*) AS count FROM appointment WHERE DATE(treatment_time) = CURDATE()")
            today_treated = cursor.fetchone()['count']

            # 待就诊数
            cursor.execute("""
                SELECT COUNT(*) AS count 
                FROM appointment 
                WHERE DATE(appointment_time) = CURDATE() AND treatment_time IS NULL
            """)
            waiting = cursor.fetchone()['count']

            # 查询挂号记录（支持搜索）
            base_sql = """
                SELECT
                    CONCAT('GH', LPAD(a.id, 5, '0')) AS registration_number,
                    p.username AS patient_name,
                    d.name AS department_name,
                    doc.name AS doctor_name,
                    DATE_FORMAT(a.appointment_time, '%%Y-%%m-%%d %%H:%%i:%%s') AS appointment_time,
                    IF(a.treatment_time IS NULL, NULL, DATE_FORMAT(a.treatment_time, '%%Y-%%m-%%d %%H:%%i:%%s')) AS treatment_time
                FROM appointment a
                JOIN patient p ON a.patient_id = p.id
                JOIN department d ON a.department_id = d.id
                JOIN doctor doc ON a.doctor_id = doc.id
                WHERE DATE(a.appointment_time) = CURDATE()
            """

            count_sql = """
                SELECT COUNT(*) AS total
                FROM appointment a
                JOIN patient p ON a.patient_id = p.id
                WHERE DATE(a.appointment_time) = CURDATE()
            """

            params = []

            # 如果有搜索关键词，加入模糊查询
            if search:
                base_sql += " AND (p.username LIKE %s OR CONCAT('GH', LPAD(a.id, 5, '0')) LIKE %s)"
                count_sql += " AND (p.username LIKE %s OR CONCAT('GH', LPAD(a.id, 5, '0')) LIKE %s)"
                like_search = f"%{search}%"
                params.extend([like_search, like_search])

            # 排序与分页
            base_sql += " ORDER BY a.appointment_time DESC LIMIT %s OFFSET %s"
            params.extend([size, offset])

            cursor.execute(base_sql, params)
            records = cursor.fetchall()

            # 查询总条数
            cursor.execute(count_sql, params[:2] if search else [])
            total = cursor.fetchone()['total']

            total_pages = (total + size - 1) // size

        return {
            "summary": {
                "today_appointments": today_appointments,
                "today_treated": today_treated,
                "waiting": waiting
            },
            "records": records,
            "pagination": {
                "page": page,
                "size": size,
                "total": total,
                "total_pages": total_pages
            }
        }

    finally:
        conn.close()


# 测试调用用例（调试使用）
if __name__ == '__main__':
    import json
    data = get_registration_data(page=1, size=10, search='')
    print(json.dumps(data, indent=2, ensure_ascii=False))
