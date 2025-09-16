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

def get_department_distribution(scope='month'):
    today = datetime.today()

    if scope == 'month':
        start_date = today.replace(day=1).strftime('%Y-%m-%d')
        next_month = (today.replace(day=28) + timedelta(days=4)).replace(day=1)
        end_date = next_month.strftime('%Y-%m-%d')
    elif scope == 'quarter':
        current_month = today.month
        quarter_start_month = 1 + 3 * ((current_month - 1) // 3)
        quarter_start = today.replace(month=quarter_start_month, day=1)
        quarter_end_month = quarter_start_month + 3
        if quarter_end_month > 12:
            quarter_end = datetime(today.year + 1, 1, 1)
        else:
            quarter_end = datetime(today.year, quarter_end_month, 1)
        start_date = quarter_start.strftime('%Y-%m-%d')
        end_date = quarter_end.strftime('%Y-%m-%d')
    else:
        start_date = (today - timedelta(days=365)).strftime('%Y-%m-%d')
        end_date = today.strftime('%Y-%m-%d')

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
        da.root_name AS name,
        COUNT(a.id) AS count
    FROM appointment a
    JOIN dept_ancestors da ON a.department_id = da.id
    WHERE a.appointment_time >= '{start_date}'
      AND a.appointment_time < '{end_date}'
      AND a.status != 1
    GROUP BY da.root_name
    ORDER BY count DESC
    LIMIT 10
    ;
    """
    return query(sql)

def get_registration_trend(scope='month'):
    today = datetime.today()

    if scope == 'month':
        start_date = today.replace(day=1).strftime('%Y-%m-%d')
        next_month = (today.replace(day=28) + timedelta(days=4)).replace(day=1)
        end_date = next_month.strftime('%Y-%m-%d')
        date_format = '%Y-%m-%d'
    elif scope == 'quarter':
        current_month = today.month
        quarter_start_month = 1 + 3 * ((current_month - 1) // 3)
        quarter_start = today.replace(month=quarter_start_month, day=1)
        quarter_end_month = quarter_start_month + 3
        if quarter_end_month > 12:
            quarter_end = datetime(today.year + 1, 1, 1)
        else:
            quarter_end = datetime(today.year, quarter_end_month, 1)
        start_date = quarter_start.strftime('%Y-%m-%d')
        end_date = quarter_end.strftime('%Y-%m-%d')
        date_format = '%Y-%m'  # 以月为单位
    else:
        start_date = (today - timedelta(days=365)).strftime('%Y-%m-%d')
        end_date = today.strftime('%Y-%m-%d')
        date_format = '%Y-%m-%d'

    sql = f"""
    SELECT
        DATE_FORMAT(appointment_time, '{date_format}') AS period,
        COUNT(id) AS count
    FROM appointment
    WHERE appointment_time >= '{start_date}'
      AND appointment_time < '{end_date}'
      AND status != 1
    GROUP BY period
    ORDER BY period;
    """
    results = query(sql)

    # 返回格式示例：{labels: [...], counts: [...]}
    labels = [row['period'] for row in results]
    counts = [row['count'] for row in results]

    return {"labels": labels, "counts": counts}


if __name__ == '__main__':
    import json

    # 这里演示调用，本月数据
    month_dist = get_department_distribution('month')
    month_trend = get_registration_trend('month')

    # 本季度数据
    quarter_dist = get_department_distribution('quarter')
    quarter_trend = get_registration_trend('quarter')

    # 按要求结构包装
    result = {
        "month": {
            "department_distribution": month_dist,
            "registration_trend": month_trend
        },
        "quarter": {
            "department_distribution": quarter_dist,
            "registration_trend": quarter_trend
        }
    }

    print(json.dumps(result, ensure_ascii=False, indent=2))