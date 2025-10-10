# 文件名: data_extractor.py (v_victory)

import requests
import json
import base64
import sqlite3

# ==============================================================================
#  配置 - 基于最终的、确切的情报
# ==============================================================================
API_URL = "https://ereklamblad.se/"
HEADERS = {
    'Content-Type': 'application/json',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36',
    'origin': 'https://ereklamblad.se',
    'referer': 'https://ereklamblad.se/'
}
DATABASE_FILE = "discounts.db"

# ==============================================================================
#  辅助函数
# ==============================================================================
def create_base64_payload(command, params):
    """
    一个更通用的函数，可以为任何指令创建Payload。
    """
    order_content = [command, params]
    json_string = json.dumps(order_content, separators=(',', ':'))
    base64_bytes = base64.b64encode(json_string.encode('utf-8'))
    base64_string = base64_bytes.decode('utf-8')
    return {"data": [base64_string]}

def parse_and_store_data(response_json, db_connection):
    """将服务器返回的纯JSON数据存入数据库。"""
    # 检查响应是否成功，以及 'value' 字段是否存在且为列表
    if response_json.get('status') != 'success' or not isinstance(response_json.get('value'), list):
        print("错误：响应状态不是'success'或'value'字段不是一个列表。")
        print("服务器原始响应:", response_json)
        return

    offers_to_process = response_json['value']
    cursor = db_connection.cursor()
    products_added = 0
    for offer in offers_to_process:
        product_id, name, price = offer.get('publicId'), offer.get('name'), offer.get('price')
        if not all([product_id, name, price]):
            continue
        
        business_info = offer.get('business', {})
        supermarket = business_info.get('name')
        
        # 提取其他有用的字段
        unit_price = offer.get('unitPrice')
        valid_from = offer.get('validFrom')
        valid_to = offer.get('validUntil')
        image_url = offer.get('image')
        description = offer.get('description')

        cursor.execute('''
            INSERT OR REPLACE INTO products (
                id, product_name, price, supermarket, 
                unit_price, valid_from, valid_to, image_url, description
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            product_id, name, float(price), supermarket,
            float(unit_price) if unit_price is not None else None,
            valid_from, valid_to, image_url, description
        ))
        products_added += 1

    db_connection.commit()
    print(f"\n胜利！ {products_added} 件商品已成功存入数据库。")

def setup_database():
    """初始化数据库，并增加新字段。"""
    with sqlite3.connect(DATABASE_FILE) as conn:
        cursor = conn.cursor()
        print(f"数据库 '{DATABASE_FILE}' 已就绪。正在检查表结构...")
        # 我们增加几个新字段来存储更丰富的信息
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS products (
                id TEXT PRIMARY KEY, product_name TEXT NOT NULL, price REAL NOT NULL,
                supermarket TEXT, unit_price REAL, valid_from TEXT, 
                valid_to TEXT, image_url TEXT, description TEXT,
                scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        # 未来可以在这里用 ALTER TABLE 增加字段，但为简单起见，重建更容易
    print("表结构检查完毕。")

# ==============================================================================
#  主程序
# ==============================================================================
if __name__ == "__main__":
    setup_database()

    # --- 1. 定义我们要使用的“万能钥匙”：一个商品的publicId ---
    # 这个ID可以作为我们获取相关推荐的“种子”
    # 我们可以从任何一个商品详情页的URL或网络请求中找到一个这样的ID
    seed_product_id = "qZ71u3lfV2E94hvsX3Ff2" 

    # --- 2. 使用我们的新发现，构建100%正确的Payload ---
    # 指令的真名是 'relatedOffers'
    payload = create_base64_payload("relatedOffers", {"publicId": seed_product_id})
    
    print(f"正在使用种子ID '{seed_product_id}' 获取相关商品列表...")
    try:
        # --- 3. 发送请求 ---
        response = requests.post(API_URL, headers=HEADERS, json=payload)
        response.raise_for_status()

        # --- 4. 直接解析返回的纯JSON ---
        response_json = json.loads(response.text.strip())
        
        # --- 5. 存入数据库 ---
        with sqlite3.connect(DATABASE_FILE) as conn:
            parse_and_store_data(response_json, conn)

    except requests.exceptions.RequestException as e:
        print(f"网络请求失败: {e}")
    except json.JSONDecodeError as e:
        print(f"解析服务器响应失败: {e}")