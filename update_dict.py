from db import get_connection

def update_dict_files():
    conn = get_connection()
    cursor = conn.cursor()

    # 导出医生名字
    cursor.execute("SELECT DISTINCT name FROM doctor")
    names = [row['name'] for row in cursor.fetchall()]
    unique_names = sorted(set(names))
    with open("dict/name.txt", "w", encoding='utf-8') as f:
        f.write("\n".join(unique_names))

    # 导出科室名字
    cursor.execute("SELECT DISTINCT name FROM department")
    departments = [row['name'] for row in cursor.fetchall()]
    unique_departments = sorted(set(departments))
    with open("dict/department.txt", "w", encoding='utf-8') as f:
        f.write("\n".join(unique_departments))

    cursor.close()
    conn.close()

if __name__ == '__main__':
    update_dict_files()
