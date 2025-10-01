# 文件名: product_search.py (v_victory)

import requests
import json
import base64
import sqlite3

# ==============================================================================
#  配置和辅助函数 (保持不变)
# ==============================================================================
API_URL = "https://ereklamblad.se/"
HEADERS = {
    'Content-Type': 'application/json',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36',
    'origin': 'https://ereklamblad.se',
    'referer': 'https://ereklamblad.se/'
}
DATABASE_FILE = "search_results.db"

def create_base64_payload(command, params):
    order_content = [command, params]
    json_string = json.dumps(order_content, separators=(',', ':'))
    base64_bytes = base64.b64encode(json_string.encode('utf-8'))
    base64_string = base64_bytes.decode('utf-8')
    return {"data": [base64_string]}

def setup_database():
    with sqlite3.connect(DATABASE_FILE) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS products (
                id TEXT PRIMARY KEY, product_name TEXT NOT NULL, price REAL,
                supermarket TEXT, unit_price REAL, valid_from TEXT, 
                valid_to TEXT, image_url TEXT, description TEXT,
                keyword TEXT, scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
    print(f"数据库 '{DATABASE_FILE}' 已就绪。")

# ==============================================================================
#  *** 核心解析函数 - 已根据最终发现进行更新 ***
# ==============================================================================
def parse_and_store_data(response_json, db_connection, keyword):
    """将搜索API返回的纯JSON数据存入数据库。"""
    # 1. 检查顶级状态是否成功
    if response_json.get('status') != 'success':
        print("错误：响应的顶级状态不是 'success'。")
        return

    # 2. 检查 'value' 和 'data' 字段是否存在
    value_dict = response_json.get('value')
    if not isinstance(value_dict, dict) or 'data' not in value_dict:
        print("错误：响应的 'value' 字段不是字典或其中缺少 'data' 键。")
        return

    offers_to_process = value_dict['data']
    if not isinstance(offers_to_process, list):
        print("错误：'value' -> 'data' 字段不是一个列表。")
        return

    cursor = db_connection.cursor()
    products_added = 0
    for offer in offers_to_process:
        # ... (数据提取逻辑和之前一样，因为商品结构是相同的) ...
        product_id, name, price = offer.get('publicId'), offer.get('name'), offer.get('price')
        if not all([product_id, name]): # 价格可能为空（比如会员价），所以暂时不作为必须项
            continue
        
        supermarket = offer.get('business', {}).get('name')
        unit_price = offer.get('unitPrice')
        valid_from = offer.get('validFrom')
        valid_to = offer.get('validUntil')
        image_url = offer.get('image')
        description = offer.get('description')
        
        # 处理价格可能为空的情况
        current_price = float(price) if price is not None else offer.get('membershipPrice')

        cursor.execute('''
            INSERT OR REPLACE INTO products (
                id, product_name, price, supermarket, 
                unit_price, valid_from, valid_to, image_url, description, keyword
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            product_id, name, current_price, supermarket,
            float(unit_price) if unit_price is not None else None,
            valid_from, valid_to, image_url, description, keyword
        ))
        products_added += 1

    db_connection.commit()
    print(f"\n胜利！ {products_added} 件关于 '{keyword}' 的商品已成功存入数据库。")

# ==============================================================================
#  主程序 - 保持不变
# ==============================================================================
if __name__ == "__main__":
    setup_database()

    search_term = input("请输入你想搜索的打折商品 (例如 mjölk, ost, bröd): ")

    if search_term:
        search_params = {
            "hideUpcoming": False,
            "pagination": {"limit": 100, "offset": 0},
            "searchTerm": search_term,
            "sort": ["score_desc"]
        }
        payload = create_base64_payload("offers", search_params)
        
        print(f"\n正在搜索 '{search_term}'...")
        try:
            response = requests.post(API_URL, headers=HEADERS, json=payload)
            response.raise_for_status()
            response_json = json.loads(response.text.strip())
            
            with sqlite3.connect(DATABASE_FILE) as conn:
                parse_and_store_data(response_json, conn, search_term)

        except Exception as e:
            print(f"程序执行出错: {e}")