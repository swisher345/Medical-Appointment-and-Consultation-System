import os
from collections import Counter

import jieba
import matplotlib.pyplot as plt
import pandas as pd
import pymysql
from wordcloud import WordCloud


def generate_doctor_wordcloud(doctor_id):
    """生成指定医生的评论词云"""

    # ================= 配置部分 =================
    # 数据库配置
    db_config = {
        'host': 'localhost',  # 数据库地址
        'user': 'root',  # 数据库用户名
        'password': 'dumengtian463',  # 数据库密码
        'database': 'doctor',  # 数据库名
        'charset': 'utf8mb4'  # 字符编码
    }

    # 文件配置
    stopwords_file = 'stopwords.txt'  # 停用词文件路径
    font_path = 'SimHei.ttf'  # 中文字体文件路径
    output_image = f'wordcloud_doctor_{doctor_id}.png'  # 输出图片名称

    # ================= 函数定义 =================
    def load_stopwords(file_path):
        """加载停用词文件"""
        stopwords = set()
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    word = line.strip()
                    if word:
                        stopwords.add(word)
            print(f"已加载 {len(stopwords)} 个停用词")
            return stopwords
        except FileNotFoundError:
            print(f"警告: 停用词文件 '{file_path}' 未找到，将使用空停用词列表")
            return set()

    def get_db_connection(config):
        """获取数据库连接"""
        try:
            conn = pymysql.connect(**config)
            print("数据库连接成功")
            return conn
        except Exception as e:
            print(f"数据库连接失败: {e}")
            return None

    def fetch_doctor_comments(conn, doctor_id):
        """获取指定医生的评论数据"""
        try:
            query = """
            SELECT comments 
            FROM sheet2 
            WHERE doctor_id = %s
            AND comments IS NOT NULL 
            AND comments != ''
            """
            df = pd.read_sql(query, conn, params=(doctor_id,))
            print(f"共获取 {len(df)} 条医生 {doctor_id} 的评论")
            return ' '.join(df['comments'].astype(str).tolist())
        except Exception as e:
            print(f"数据查询失败: {e}")
            return ""

    def process_text(text, stopwords):
        """处理文本并生成词频"""
        if not text:
            return None

        # 中文分词
        words = jieba.cut(text)

        # 过滤停用词和短词
        filtered_words = [
            word for word in words
            if len(word) > 1 and word not in stopwords
        ]

        # 统计词频
        word_freq = Counter(filtered_words)
        print(f"处理后得到 {len(word_freq)} 个有效词语")
        return word_freq

    def generate_wordcloud(word_freq, doctor_id, font_path=None):
        """生成词云"""
        try:
            wc = WordCloud(
                font_path=font_path,
                width=800,
                height=600,
                background_color='white',
                max_words=200,
                collocations=False,
                prefer_horizontal=0.9
            )
            wc.generate_from_frequencies(word_freq)

            # 添加医生ID标题
            plt.figure(figsize=(12, 8))
            plt.imshow(wc, interpolation='bilinear')
            plt.title(f"医生ID: {doctor_id} 的评论词云", fontsize=16)
            plt.axis('off')

            # 保存图片
            wc.to_file(output_image)
            print(f"词云已保存为: {output_image}")

            plt.show()
            return True
        except Exception as e:
            print(f"生成词云失败: {e}")
            return False

    # ================= 主程序 =================
    # 1. 加载停用词
    stopwords = load_stopwords(stopwords_file)

    # 2. 连接数据库
    conn = get_db_connection(db_config)
    if conn is None:
        return False

    try:
        # 3. 获取指定医生的评论数据
        text = fetch_doctor_comments(conn, doctor_id)
        if not text:
            print(f"未找到医生 {doctor_id} 的有效评论数据")
            return False

        # 4. 处理文本
        word_freq = process_text(text, stopwords)
        if not word_freq:
            print("处理后无有效词语")
            return False

        # 5. 检查字体文件
        if font_path and not os.path.exists(font_path):
            print(f"警告: 字体文件 '{font_path}' 不存在，将尝试使用默认字体")
            font_path = None

        # 6. 生成并保存词云
        return generate_wordcloud(word_freq, doctor_id, font_path)

    finally:
        conn.close()
        print("数据库连接已关闭")


if __name__ == "__main__":
    # 示例：生成医生ID为123的词云
    doctor_id = input("请输入要生成词云的医生ID: ")
    generate_doctor_wordcloud(doctor_id)