import pymysql
db_config = {
    'host': 'localhost',
    'user': 'root', # mysql 用户
    'password': 'dumengtian463', # mysql 密码
    'database': 'hospital8', # 连接hospotal（医院）框架
    'charset': 'utf8mb4',
    'cursorclass': pymysql.cursors.DictCursor
}
# 数据库基本信息