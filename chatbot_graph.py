#!/usr/bin/env python3
# coding: utf-8
# File: chatbot_graph.py
# Author: lhy<lhy_in_blcu@126.com,https://huangyong.github.io>
# Date: 18-10-4

import json

import requests

from answer_search import *
from question_classifier import *
from question_parser import *

'''问答类'''


class ChatBotGraph:
    def __init__(self):
        self.classifier = QuestionClassifier()
        self.parser = QuestionPaser()
        self.searcher = AnswerSearcher()
        # DeepSeek API配置
        self.deepseek_api_key = "sk-049f898dfbd14e22a458d8d2d9679ba9"  # 替换为您的DeepSeek API密钥
        self.deepseek_url = "https://api.deepseek.com/chat/completions"

    def call_deepseek_api(self, question):
        """调用DeepSeek API获取答案"""
        headers = {
            "Authorization": f"Bearer {self.deepseek_api_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": "你是一个专业的医药智能助理，请用中文回答医疗健康相关问题"},
                {"role": "user", "content": question}
            ],
            "temperature": 0.7,
            "max_tokens": 1024
        }

        try:
            response = requests.post(
                self.deepseek_url,
                headers=headers,
                data=json.dumps(payload),
                timeout=50  # 设置超时时间
            )
            if response.status_code == 200:
                result = response.json()
                return result['choices'][0]['message']['content'].strip()
            return f"抱歉，我暂时无法回答这个问题。"
        except Exception as e:
            return f"网络连接出现问题，请尝试访问https://www.doubao.com/或咨询专业医生。"

    def chat_main(self, sent):
        answer = '您好，我是医药智能助理，希望可以帮到您。如果没答上来，可联系https://www.doubao.com/。祝您身体棒棒！'
        res_classify = self.classifier.classify(sent)
        from_api = False

        # 分类失败时调用DeepSeek API
        if not res_classify:
            answer = self.call_deepseek_api(sent)  # 调用API获取答案
            from_api = True
        else:
            res_sql = self.parser.parser_main(res_classify)
            final_answers = self.searcher.search_main(res_sql)

            if not final_answers:
                answer = self.call_deepseek_api(sent)  # 无结果时也调用API
                from_api = True
            else:
                answer = '\n'.join(final_answers)

        return answer, from_api


if __name__ == '__main__':
    handler = ChatBotGraph()
    while 1:
        question = input('用户:')
        answer, from_api = handler.chat_main(question)
        print('助手:', answer)
        if from_api:
            print('此回答来自DeepSeek调用')