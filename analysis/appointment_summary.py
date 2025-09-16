from datetime import datetime, timedelta

import pymysql

DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': 'dumengtian463',
    'database': 'hospital1',
    'charset': 'utf8mb4',
    'cursorclass': pymysql.cursors.DictCursor
}

def query(sql):
    connection = pymysql.connect(**DB_CONFIG)
    try:
        with connection.cursor() as cursor:
            cursor.execute(sql)
            return cursor.fetchall()
    finally:
        connection.close()

def get_appointment_count(start_date, end_date):
    sql = f"""
        SELECT COUNT(*) AS count
        FROM appointment
        WHERE appointment_time >= '{start_date}' AND appointment_time < '{end_date}'
          AND status != 1
    """
    result = query(sql)
    return result[0]['count'] if result else 0

def get_parent_department_ranking(start_date, end_date):
    sql = f"""
    WITH RECURSIVE dept_ancestors AS (
        SELECT id, name, parent_id, id AS root_id, name AS root_name
        FROM department
        WHERE parent_id IS NULL
        UNION ALL
        SELECT d.id, d.name, d.parent_id, da.root_id, da.root_name
        FROM department d
        JOIN dept_ancestors da ON d.parent_id = da.id
    )
    SELECT
        da.root_id AS parent_department_id,
        da.root_name AS parent_department_name,
        COUNT(a.id) AS appointment_count
    FROM appointment a
    JOIN dept_ancestors da ON a.department_id = da.id
    WHERE a.appointment_time >= '{start_date}'
      AND a.appointment_time < '{end_date}'
      AND a.status != 1
    GROUP BY da.root_id, da.root_name
    ORDER BY appointment_count DESC
    LIMIT 3;
    """
    return query(sql)

def get_statistics():
    today = datetime.today()

    # 本月起止日期
    month_start = today.replace(day=1).strftime('%Y-%m-%d')
    next_month = (today.replace(day=28) + timedelta(days=4)).replace(day=1)
    month_end = next_month.strftime('%Y-%m-%d')

    # 本季度起止日期
    current_month = today.month
    quarter_start_month = 1 + 3 * ((current_month - 1) // 3)
    quarter_start = today.replace(month=quarter_start_month, day=1)
    quarter_end_month = quarter_start_month + 3
    if quarter_end_month > 12:
        quarter_end = datetime(today.year + 1, 1, 1)
    else:
        quarter_end = datetime(today.year, quarter_end_month, 1)

    quarter_start_str = quarter_start.strftime('%Y-%m-%d')
    quarter_end_str = quarter_end.strftime('%Y-%m-%d')

    # 获取统计数据
    month_total = get_appointment_count(month_start, month_end)
    quarter_total = get_appointment_count(quarter_start_str, quarter_end_str)

    month_days = (datetime.strptime(month_end, '%Y-%m-%d') - datetime.strptime(month_start, '%Y-%m-%d')).days
    quarter_days = (quarter_end - quarter_start).days

    month_ranking = get_parent_department_ranking(month_start, month_end)
    quarter_ranking = get_parent_department_ranking(quarter_start_str, quarter_end_str)

    return {
        "month": {
            "start_date": month_start,
            "end_date": month_end,
            "total_appointments": month_total,
            "average_daily_appointments": round(month_total / month_days, 2) if month_days > 0 else 0,
            "top_departments": month_ranking
        },
        "quarter": {
            "start_date": quarter_start_str,
            "end_date": quarter_end_str,
            "total_appointments": quarter_total,
            "average_daily_appointments": round(quarter_total / quarter_days, 2) if quarter_days > 0 else 0,
            "top_departments": quarter_ranking
        }
    }

def get_summary_data():
    stats = get_statistics()

    def format_summary(period_stats):
        total = period_stats['total_appointments']
        top_depts = period_stats['top_departments']
        if top_depts:
            top_dept = top_depts[0]['parent_department_name']
            top_count = top_depts[0]['appointment_count']
            top_percentage = round(top_count / total * 100, 2) if total > 0 else 0
        else:
            top_dept = ''
            top_percentage = 0

        return {
            "total_registrations": total,
            "daily_average": period_stats['average_daily_appointments'],
            "top_department": top_dept,
            "top_department_percentage": top_percentage
        }

    return {
        "month": format_summary(stats['month']),
        "quarter": format_summary(stats['quarter'])
    }


if __name__ == "__main__":
    import json
    summary = get_summary_data()
    print("本月统计:")
    print(json.dumps(summary['month'], ensure_ascii=False, indent=2))
    print("\n本季度统计:")
    print(json.dumps(summary['quarter'], ensure_ascii=False, indent=2))
