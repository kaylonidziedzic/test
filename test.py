import requests

API_URL = "http://localhost:12673/v1/proxy"
API_KEY = "change_me_please"  # 对应 config.py 里的设置

payload = {
    "url": "https://nowsecure.in",
    "method": "GET"
}

headers = {
    "X-API-KEY": API_KEY
}

resp = requests.post(API_URL, json=payload, headers=headers)
print(resp.json()['text']) # 直接打印目标网站内容
