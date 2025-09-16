# speech_recognizer.py
import base64
import hashlib
import hmac
import json
import ssl
import threading
import time
from datetime import datetime
from time import mktime
from urllib.parse import urlencode
from wsgiref.handlers import format_date_time

import websocket

# 讯飞WebSocket地址
WS_URL = 'wss://ws-api.xfyun.cn/v2/iat'


class Ws_Param(object):
    def __init__(self, appid, apikey, apisecret):
        self.APPID = appid
        self.APIKey = apikey
        self.APISecret = apisecret
        self.CommonArgs = {"app_id": self.APPID}
        self.BusinessArgs = {
            "domain": "iat",
            "language": "zh_cn",
            "accent": "mandarin",
            "vinfo": 1,
            "vad_eos": 10000
        }

    def create_url(self):
        url = WS_URL
        now = datetime.now()
        date = format_date_time(mktime(now.timetuple()))

        signature_origin = "host: ws-api.xfyun.cn\n"
        signature_origin += "date: " + date + "\n"
        signature_origin += "GET /v2/iat HTTP/1.1"

        signature_sha = hmac.new(
            self.APISecret.encode('utf-8'),
            signature_origin.encode('utf-8'),
            digestmod=hashlib.sha256
        ).digest()
        signature_sha = base64.b64encode(signature_sha).decode('utf-8')

        authorization_origin = f'api_key="{self.APIKey}", algorithm="hmac-sha256", headers="host date request-line", signature="{signature_sha}"'
        authorization = base64.b64encode(authorization_origin.encode('utf-8')).decode('utf-8')

        v = {
            "authorization": authorization,
            "date": date,
            "host": "ws-api.xfyun.cn"
        }
        url = url + '?' + urlencode(v)
        return url


class SpeechRecognizer:
    def __init__(self, appid, apikey, apisecret, audio_bytes):
        self.ws_param = Ws_Param(appid, apikey, apisecret)
        self.audio_bytes = audio_bytes
        self.result_text = ''
        self.event = threading.Event()

    def on_message(self, ws, message):
        try:
            msg = json.loads(message)
            code = msg.get('code')
            sid = msg.get('sid')
            if code != 0:
                errMsg = msg.get('message')
                print(f"sid:{sid} call error: {errMsg} code is:{code}")
                self.event.set()
            else:
                data = msg.get('data', {}).get('result', {}).get('ws', [])
                for w in data:
                    for cw in w.get('cw', []):
                        self.result_text += cw.get('w', '')
                if msg.get('data', {}).get('status') == 2:
                    self.event.set()
        except Exception as e:
            print("receive msg,but parse exception:", e)
            self.event.set()

    def on_error(self, ws, error):
        print("### error:", error)
        self.event.set()

    def on_close(self, ws, close_status_code, close_msg):
        print("### closed ###")

    def on_open(self, ws):
        def run():
            frame_size = 1280  # 16k采样率，16bit，每帧80ms左右音频
            interval = 0.04  # 40ms
            status = 0  # 0=first frame, 1=continue, 2=last frame

            data_len = len(self.audio_bytes)
            index = 0
            while True:
                if index >= data_len:
                    status = 2  # last frame
                if status == 0:
                    chunk = self.audio_bytes[index:index + frame_size]
                    d = {
                        "common": self.ws_param.CommonArgs,
                        "business": self.ws_param.BusinessArgs,
                        "data": {
                            "status": 0,
                            "format": "audio/L16;rate=16000",
                            "audio": str(base64.b64encode(chunk), 'utf-8'),
                            "encoding": "raw"
                        }
                    }
                    ws.send(json.dumps(d))
                    status = 1
                    index += frame_size
                elif status == 1:
                    chunk = self.audio_bytes[index:index + frame_size]
                    if not chunk:
                        status = 2
                        continue
                    d = {
                        "data": {
                            "status": 1,
                            "format": "audio/L16;rate=16000",
                            "audio": str(base64.b64encode(chunk), 'utf-8'),
                            "encoding": "raw"
                        }
                    }
                    ws.send(json.dumps(d))
                    index += frame_size
                elif status == 2:
                    d = {
                        "data": {
                            "status": 2,
                            "format": "audio/L16;rate=16000",
                            "audio": "",
                            "encoding": "raw"
                        }
                    }
                    ws.send(json.dumps(d))
                    break
                time.sleep(interval)
            time.sleep(1)
            ws.close()

        threading.Thread(target=run).start()

    def recognize(self):
        ws_url = self.ws_param.create_url()
        ws = websocket.WebSocketApp(
            ws_url,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close
        )
        ws.on_open = self.on_open
        ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE})

        self.event.wait(timeout=15)
        return self.result_text
