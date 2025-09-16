from datetime import datetime, timedelta
from decimal import Decimal

import pandas as pd
import pymysql
from dateutil.relativedelta import relativedelta  # 新增导入

DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': 'dumengtian463',
    'database': 'hospital1',
    'charset': 'utf8mb4',
    'cursorclass': pymysql.cursors.DictCursor
}

def get_daily_stats(start_date, end_date):
    conn = pymysql.connect(**DB_CONFIG)
    try:
        with conn.cursor() as cursor:
            cursor.execute(f"""
                WITH RECURSIVE dept_tree AS (
                    SELECT id, name, parent_id, name AS root_name FROM department WHERE parent_id IS NULL
                    UNION ALL
                    SELECT d.id, d.name, d.parent_id, dt.root_name
                    FROM department d
                    JOIN dept_tree dt ON d.parent_id = dt.id
                ),
                appointment_data AS (
                    SELECT 
                        DATE(a.appointment_time) AS date,
                        dt.root_name AS parent_department_name
                    FROM appointment a
                    JOIN dept_tree dt ON a.department_id = dt.id
                    WHERE a.status != 1
                    AND a.appointment_time BETWEEN '{start_date}' AND '{end_date}'
                ),
                daily_counts AS (
                    SELECT 
                        date,
                        COUNT(*) AS total,
                        parent_department_name
                    FROM appointment_data
                    GROUP BY date, parent_department_name
                )
                SELECT 
                    date,
                    SUM(total) AS registration_count,
                    (SELECT parent_department_name
                     FROM daily_counts dc2
                     WHERE dc2.date = dc1.date
                     ORDER BY total DESC LIMIT 1) AS top_department
                FROM daily_counts dc1
                GROUP BY date
                ORDER BY date
            """)
            return cursor.fetchall()
    finally:
        conn.close()

def convert_decimal_in_list(data):
    new_data = []
    for item in data:
        new_item = {}
        for k, v in item.items():
            if isinstance(v, Decimal):
                new_item[k] = float(v)
            else:
                new_item[k] = v
        new_data.append(new_item)
    return new_data

def compute_yoy_growth(data):
    df = pd.DataFrame(data)
    if df.empty:
        return []
    df['date'] = pd.to_datetime(df['date'])

    results = []

    for i, row in df.iterrows():
        date = row['date']
        reg_count = row['registration_count']
        top_dept = row['top_department']

        prev_date = date - relativedelta(months=1)
        prev_row = df[df['date'] == prev_date]

        if not prev_row.empty:
            prev_count = prev_row.iloc[0]['registration_count']
            growth = ((reg_count - prev_count) / prev_count) * 100 if prev_count > 0 else None
        else:
            growth = None

        results.append({
            'date': date.strftime('%Y-%m-%d'),
            'count': float(reg_count),
            'top_department': top_dept,
            'growth_rate': round(growth, 1) if growth is not None else None
        })

    return convert_decimal_in_list(results)

# def get_registration_details():
#     today = datetime.today()
#
#     # 本月开始和结束
#     month_start = today.replace(day=1)
#     next_month = (month_start + timedelta(days=32)).replace(day=1)  # 下个月1号
#     month_end = next_month - timedelta(days=1)  # 本月最后一天
#
#     # 上个月开始
#     last_month = (month_start - timedelta(days=1)).replace(day=1)
#
#     # 本季度范围
#     current_month = today.month
#     quarter_start_month = 1 + 3 * ((current_month - 1) // 3)
#     quarter_start = today.replace(month=quarter_start_month, day=1)
#     quarter_end_month = quarter_start_month + 3
#     if quarter_end_month > 12:
#         quarter_end = datetime(today.year + 1, 1, 1)
#     else:
#         quarter_end = datetime(today.year, quarter_end_month, 1)
#
#     # 本月时间段扩大为“上个月开始”到“本月结束”，保证包含上月数据
#     month_data = get_daily_stats(last_month.strftime('%Y-%m-%d'), month_end.strftime('%Y-%m-%d'))
#
#     # 本季度时间段只取季度范围
#     quarter_data = get_daily_stats(quarter_start.strftime('%Y-%m-%d'), quarter_end.strftime('%Y-%m-%d'))
#
#     month_details = compute_yoy_growth(month_data)
#
#     # 只保留本月数据（去掉上月，只展示本月的行）
#     month_details = [item for item in month_details if item['date'] >= month_start.strftime('%Y-%m-%d')]
#
#     quarter_details = compute_yoy_growth(quarter_data)
#
#     return {
#         "month": month_details,
#         "quarter": quarter_details
#     }

def get_registration_details():
    today = datetime.today()

    # 本月
    month_start = today.replace(day=1)
    next_month = (month_start + timedelta(days=32)).replace(day=1)
    month_end = next_month - timedelta(days=1)
    last_month = (month_start - timedelta(days=1)).replace(day=1)

    # 本季度
    current_month = today.month
    quarter_start_month = 1 + 3 * ((current_month - 1) // 3)
    quarter_start = today.replace(month=quarter_start_month, day=1)
    quarter_end_month = quarter_start_month + 3
    quarter_end = datetime(today.year + 1, 1, 1) if quarter_end_month > 12 else datetime(today.year, quarter_end_month, 1)
    quarter_prev_month_start = (quarter_start - timedelta(days=1)).replace(day=1)

    # 月数据（含上月）
    month_data = get_daily_stats(last_month.strftime('%Y-%m-%d'), month_end.strftime('%Y-%m-%d'))
    month_details = compute_yoy_growth(month_data)
    month_details = [item for item in month_details if item['date'] >= month_start.strftime('%Y-%m-%d')]

    # 季度数据（含上月）
    quarter_data = get_daily_stats(quarter_prev_month_start.strftime('%Y-%m-%d'), quarter_end.strftime('%Y-%m-%d'))
    quarter_details = compute_yoy_growth(quarter_data)
    quarter_details = [item for item in quarter_details if item['date'] >= quarter_start.strftime('%Y-%m-%d')]

    return {
        "month": month_details,
        "quarter": quarter_details
    }



if __name__ == '__main__':
    import json
    details = get_registration_details()
    print(json.dumps(details, ensure_ascii=False, indent=2))
