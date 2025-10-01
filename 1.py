import requests
import json
import sqlite3
from datetime import datetime

# ==============================================================================
#  配置 - 保持不变
# ==============================================================================

API_URL = "https://ereklamblad.se/"

# 这是正确的 payload_data
payload_data = {
    "data": [
        "WyJvZmZlciIseyJwdWJsaWNJZCI6InJfVE1rVnNEUE5ZWmVwVlJhVGJ2cyJ9XQ==",
        "WyJyZWxhdGVkT2ZmZXJzIix7InB1YmxpY0lkIjoicl9UTWtWc0RQTllaZXBWUmFUYnZzIn1d"
    ]
}

HEADERS = {
    'Content-Type': 'application/json',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36',
    'origin': 'https://ereklamblad.se',
    'referer': 'https://ereklamblad.se/'
}

DATABASE_FILE = "discounts.db"

# ==============================================================================
#  函数 - *** 这里的 fetch_data_from_api 函数已更新 ***
# ==============================================================================

def fetch_data_from_api(url, payload):
    """
    发送POST请求。这个版本现在可以处理服务器返回的、
    由多个JSON对象组成的响应。
    """
    print(f"发送 POST 请求到: {url}")
    print(f"附带的 Payload: {json.dumps(payload, indent=2)}")
    try:
        response = requests.post(url, headers=HEADERS, json=payload)
        response.raise_for_status()
        print("成功接收到响应！开始解析...")

        # --- 这是新的解决方案 ---
        # 1. 创建一个空列表，用来存放所有解析成功的JSON对象
        all_json_objects = []
        
        # 2. 获取原始的文本响应，并按行分割
        #    .strip() 会移除开头和结尾的空白
        #    .split('\n') 会把文本分割成一个行的列表
        for line in response.text.strip().split('\n'):
            # 3. 尝试将每一行都解析成一个独立的JSON对象
            try:
                # 如果行不为空，就进行解析
                if line:
                    json_obj = json.loads(line)
                    all_json_objects.append(json_obj)
            except json.JSONDecodeError:
                # 如果某一行不是有效的JSON（比如空行），就忽略它
                print(f"警告：无法解析此行，已跳过: {line[:50]}...")
                continue
        
        print(f"解析完成！共找到 {len(all_json_objects)} 个JSON对象。")
        return all_json_objects # 返回包含所有对象的列表

    except requests.exceptions.RequestException as e:
        print(f"请求失败: {e}")
        return None

# parse_and_store_data 和 setup_database 函数保持不变
def parse_and_store_data(data, db_connection):
    if not data or not isinstance(data, list):
        print("接收到的数据格式不正确或为空，跳过处理。")
        return

    cursor = db_connection.cursor()
    products_added = 0

    for item in data:
        if item.get("status") == "success" and "value" in item:
            value = item["value"]
            offers_to_process = []
            if isinstance(value, list):
                offers_to_process.extend(value)
            elif isinstance(value, dict):
                offers_to_process.append(value)
            
            for offer in offers_to_process:
                if not isinstance(offer, dict):
                    continue

                product_id = offer.get('publicId')
                product_name = offer.get('name')
                price = offer.get('price')
                if price is None:
                    continue
                
                supermarket = offer.get('business', {}).get('name')
                valid_from_str = offer.get('validFrom')
                valid_until_str = offer.get('validUntil')
                image_url = offer.get('image')

                if not all([product_id, product_name, supermarket]):
                    continue
                
                try:
                    valid_from = datetime.fromisoformat(valid_from_str.replace('+0000', '+00:00')).strftime('%Y-%m-%d') if valid_from_str else None
                    valid_until = datetime.fromisoformat(valid_until_str.replace('+0000', '+00:00')).strftime('%Y-%m-%d') if valid_until_str else None
                except (ValueError, TypeError):
                    valid_from = None
                    valid_until = None

                cursor.execute('''
                    INSERT OR REPLACE INTO products (id, product_name, price, supermarket, valid_from, valid_to, image_url)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                ''', (product_id, product_name, float(price), supermarket, valid_from, valid_until, image_url))
                
                products_added += 1

    db_connection.commit()
    print(f"处理完成！ {products_added} 件商品被添加或更新到数据库。")


def setup_database():
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id TEXT PRIMARY KEY,
            product_name TEXT NOT NULL,
            price REAL,
            supermarket TEXT NOT NULL,
            valid_from DATE,
            valid_to DATE,
            image_url TEXT,
            scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()
    print(f"数据库 '{DATABASE_FILE}' 已准备就绪。")

# ==============================================================================
#  主程序入口 - 保持不变
# ==============================================================================

if __name__ == "__main__":
    setup_database()
    api_data = fetch_data_from_api(API_URL, payload_data)

    if api_data:
        try:
            with sqlite3.connect(DATABASE_FILE) as conn:
                print(f"已连接到数据库 '{DATABASE_FILE}' 进行数据存储。")
                parse_and_store_data(api_data, conn)
        except sqlite3.Error as e:
            print(f"数据库操作失败: {e}")