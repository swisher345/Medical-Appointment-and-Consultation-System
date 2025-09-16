# search.py
import difflib
import re  # ✅ 新增
from collections import defaultdict

import jieba
import pymysql
from pypinyin import lazy_pinyin
from spellchecker import SpellChecker

from db import get_connection
from update_dict import update_dict_files

spell = SpellChecker()

# 动词字典，可以根据需要扩展
VERB_DICT = [
    "帮我找", "帮忙找", "帮我查", "我要查", "帮我看看", "我要找",
    "找", "查找", "搜索", "看看"
]

# 职称列表，匹配后从末尾去除
TITLE_LIST = ["医生", "护士", "主任", "专家", "学者", "教授", "顾问"]

def get_all_doctors():
    conn = get_connection()
    cursor = conn.cursor(pymysql.cursors.DictCursor)
    try:
        cursor.execute("SELECT * FROM doctor")
        return cursor.fetchall()
    except Exception as e:
        print(f"数据库查询失败: {e}")
        return []
    finally:
        conn.close()

def load_names(filename):
    with open(filename, 'r', encoding='utf-8') as f:
        return [line.strip() for line in f if line.strip()]

def get_pinyin(text: str) -> str:
    """将中文转为拼音，不含声调"""
    return ''.join(lazy_pinyin(text))

def get_similarity_pinyin(p1: str, p2: str) -> float:
    return difflib.SequenceMatcher(None, p1, p2).ratio()

def preprocess_input(user_input: str) -> str:
    """
    1. 去掉标点符号；
    2. 去掉动词前缀；
    3. 去掉末尾职称后缀；
    4. 返回纯粹的姓名关键词。
    """
    text = user_input.strip()

    # ✅ 1. 去除中文英文标点符号
    text = re.sub(r'[^\w\u4e00-\u9fff]', '', text)

    # 2. 动词截取
    for verb in sorted(VERB_DICT, key=len, reverse=True):
        if text.startswith(verb):
            text = text[len(verb):].strip()
            break

    # 3. 职称去除
    for title in TITLE_LIST:
        if text.endswith(title):
            text = text[: -len(title)].strip()

    return text

def search_names(user_input: str, names_file: str = r'dict\name.txt', top_n: int = 5):
    update_dict_files()

    keywords = preprocess_input(user_input)
    names_list = load_names(names_file)
    kw_pinyin = get_pinyin(keywords)

    score_map = defaultdict(float)

    # ③ 中文完全匹配
    for name in names_list:
        if keywords == name:
            score_map[name] += 5.0

    # ④ 拼音全等匹配
    for name in names_list:
        name_py = get_pinyin(name)
        if kw_pinyin == name_py:
            score_map[name] += 4.0

    # ⑤ 开头匹配
    for name in names_list:
        name_py = get_pinyin(name)
        if name.startswith(keywords):
            score_map[name] += 3.0
        if name_py.startswith(kw_pinyin):
            score_map[name] += 2.0

    # ⑥ 拼音相似度
    for name in names_list:
        name_py = get_pinyin(name)
        sim = get_similarity_pinyin(kw_pinyin, name_py)
        if sim > 0.6:
            score_map[name] += sim

    # ⑦ 分词模糊匹配
    if len(keywords) >= 5:
        parts = list(jieba.cut(keywords))
        for part in parts:
            part_py = get_pinyin(part)
            for name in names_list:
                name_py = get_pinyin(name)
                if name.startswith(part):
                    score_map[name] += 1.0
                sim = get_similarity_pinyin(part_py, name_py)
                if sim > 0.5:
                    score_map[name] += sim

    # ⑧ 排序
    sorted_items = sorted(score_map.items(), key=lambda x: x[1], reverse=True)
    # print(sorted_items)
    # ---- 根据得分判断返回数量 ----
    high_score_candidates = [item for item in sorted_items if item[1] > 1]

    if high_score_candidates:
        best_name = high_score_candidates[0][0]
        return [best_name]
    else:
        final = [name for name, score in sorted_items if score > 0][:top_n]
        return final

if __name__ == '__main__':
    tests = [
        "喂喂喂，我要找张建国医生！",
        "帮我搜索李四主任。",
        "找张三护士~",
        "看看赵六专家！",
        "王医生？",
        "找王医生！"
    ]
    for q in tests:
        print(f"输入: {q}  =>  返回: {search_names(q)}")
