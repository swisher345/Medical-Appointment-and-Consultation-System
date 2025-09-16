import os

import pymysql
from pymysql import MySQLError


def import_doctor_images():
    # 数据库配置
    db_config = {
        'host': 'localhost',
        'user': 'root',
        'password': '123456',
        'db': 'hospital',
        'charset': 'utf8mb4'
    }

    # 图片文件夹路径（请根据实际情况修改）
    image_dir = r'D:\PyCharm\Py_Projects\Final exam\static'

    try:
        # 获取所有PNG文件并按文件名排序（确保循环顺序一致）
        image_files = [
            f for f in os.listdir(image_dir)
            if f.lower().endswith('.png')
        ]

        # 按文件名排序，确保循环顺序一致
        image_files.sort()

        if not image_files:
            print("错误：未找到任何PNG图片文件")
            return

        # 确保至少有一张图片
        if len(image_files) == 0:
            print("错误：图片文件夹中没有PNG文件")
            return

        print(f"找到 {len(image_files)} 张PNG图片: {', '.join(image_files)}")

        # 连接数据库
        conn = pymysql.connect(**db_config)

        with conn.cursor() as cursor:
            # 获取所有医生记录的ID
            cursor.execute("SELECT id FROM doctor")
            doctor_ids = [row[0] for row in cursor.fetchall()]

            total_doctors = len(doctor_ids)
            total_images = len(image_files)

            if total_doctors == 0:
                print("错误：sheet1表中没有医生记录")
                return

            print(f"找到 {total_doctors} 位医生记录")

            # 循环使用图片的逻辑
            success_count = 0
            for i, doctor_id in enumerate(doctor_ids, 1):
                try:
                    # 循环获取图片（使用取模运算实现循环）
                    image_index = (i - 1) % total_images  # 修正索引计算（从0开始）
                    image_file = image_files[image_index]
                    image_path = os.path.join(image_dir, image_file)

                    # 验证图片存在且可读
                    if not os.path.exists(image_path):
                        print(f"警告：文件不存在 - {image_path}，跳过")
                        continue

                    with open(image_path, 'rb') as f:
                        image_data = f.read()

                    # 执行更新
                    cursor.execute(
                        "UPDATE doctor SET picture = %s WHERE id = %s",
                        (image_data, doctor_id)
                    )
                    success_count += 1

                    # 输出进度，每10条记录或最后一条时显示
                    if i % 10 == 0 or i == total_doctors:
                        print(f"进度: {i}/{total_doctors} - "
                              f"使用图片 {image_file} 更新ID {doctor_id}")

                except Exception as file_error:
                    print(f"处理图片 {image_file} 时出错: {str(file_error)}")
                    continue

            conn.commit()
            print(f"\n操作完成: 成功更新 {success_count} 条记录的图片")
            print(f"图片循环使用情况: 每张图片平均使用 {total_doctors / total_images:.2f} 次")
            if total_doctors > total_images:
                print(f"提示：{total_doctors - success_count} 条记录因图片循环使用已覆盖")

    except MySQLError as e:
        print(f"数据库错误: {e}")
    except Exception as e:
        print(f"程序错误: {e}")
    finally:
        if 'conn' in locals() and conn.open:
            conn.close()


if __name__ == "__main__":
    import_doctor_images()