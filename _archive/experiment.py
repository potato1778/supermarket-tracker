# 文件名: experiment.py (v_search_reveal)

import requests
import json
import base64

API_URL = "https://ereklamblad.se/"
HEADERS = {
    'Content-Type': 'application/json',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36',
    'origin': 'https://ereklamblad.se',
    'referer': 'https://ereklamblad.se/'
}

def create_base64_payload(command, params):
    order_content = [command, params]
    json_string = json.dumps(order_content, separators=(',', ':'))
    base64_bytes = base64.b64encode(json_string.encode('utf-8'))
    base64_string = base64_bytes.decode('utf-8')
    return {"data": [base64_string]}

# --- 我们的最终确认实验 ---

# 1. 定义我们要搜索的关键词
search_term = "mjölk"

# 2. 构建我们已破解的搜索Payload
search_params = {
    "hideUpcoming": False,
    "pagination": {"limit": 24, "offset": 0}, # 先获取24个看看结构
    "searchTerm": search_term,
    "sort": ["score_desc"]
}
payload = create_base64_payload("offers", search_params)

print(f"--- 正在为搜索 '{search_term}' 发送请求 ---")
try:
    # 3. 发送请求
    response = requests.post(API_URL, headers=HEADERS, json=payload)
    response.raise_for_status()

    # 4. 直接解析返回的纯JSON，并格式化打印
    print("\n--- 成功从服务器收到搜索结果的JSON响应 ---")
    response_json = json.loads(response.text.strip())
    print(json.dumps(response_json, indent=2))
    print("---------------------------------------")

except Exception as e:
    print(f"程序执行出错: {e}")

### **行动指令 (最后一次侦察！)**

