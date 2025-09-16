import re

import jieba

# 初始化jieba分词
jieba.initialize()

# 自定义词典 - 添加医疗相关词汇
jieba.add_word('临床经验')
jieba.add_word('从医历程')
jieba.add_word('医疗实践')


def extract_keyworks(text):
    """
    从医生简介中提取精准关键词
    格式示例：医师，儿科，22年临床经验
    """
    if not text or not isinstance(text, str):
        return []

    # 1. 提取职称
    title = extract_title(text)

    # 2. 提取科室
    department = extract_department(text)

    # 3. 提取工作年限
    years_exp = extract_years_experience(text)

    # 组合关键词
    keyworks = []
    if title:
        keyworks.append(title)
    if department:
        keyworks.append(department)
    if years_exp:
        keyworks.append(f"{years_exp}年临床经验")

    return keyworks


def extract_title(text):
    """提取职称"""
    titles = ['医师', '主治医师', '副主任医师', '主任医师', '住院医师']
    for title in titles:
        if title in text:
            return title
    return None


def extract_department(text):
    """提取科室"""
    departments = [
        '儿科', '妇产科', '内科', '外科', '口腔科', '眼科',
        '耳鼻喉科', '皮肤科', '神经科', '心血管科', '呼吸科',
        '消化科', '内分泌科', '泌尿外科', '骨科', '肿瘤科'
    ]
    for dept in departments:
        if dept in text:
            return dept
    return None


def extract_years_experience(text):
    """提取工作年限"""
    # 模式1: "在过去的22年里"
    match = re.search(r'在过去的(\d+)年', text)
    if match:
        return match.group(1)

    # 模式2: "22年的从医历程"
    match = re.search(r'(\d+)年的从医历程', text)
    if match:
        return match.group(1)

    # 模式3: "22年的医疗实践"
    match = re.search(r'(\d+)年的医疗实践', text)
    if match:
        return match.group(1)

    # 模式4: "工作22年"
    match = re.search(r'工作(\d+)年', text)
    if match:
        return match.group(1)

    return None


def extract_keyworks_from_all(text_list):
    """
    从多个文本字段中提取关键词并合并
    :param text_list: 文本列表 [专长文本, 简介文本]
    :return: 合并后的关键词字符串
    """
    all_keyworks = []
    for text in text_list:
        if text:
            all_keyworks.extend(extract_keyworks(text))

    # 去重并保留顺序
    seen = set()
    unique_keyworks = []
    for kw in all_keyworks:
        if kw not in seen:
            seen.add(kw)
            unique_keyworks.append(kw)

    return ', '.join(unique_keyworks) if unique_keyworks else '' 