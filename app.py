# app.py (Final Version)

from flask import Flask, render_template, request, jsonify
from flask_cors import CORS

# 明确地导入我们需要的函数，而不是用 *
from api_communicator import create_search_payload, fetch_search_results
from database_manager import setup_database, store_products

# 创建Flask应用实例
app = Flask(__name__)
# 为应用开启CORS，允许前端访问
CORS(app)

# ==============================================================================
# "数据清洗车间" - 采纳了你的所有建议
# ==============================================================================
def clean_and_prepare_products(raw_product_list):
    """
    接收原始的商品列表，按照最精密的规则，清洗并标准化它。
    这是保证前后端数据一致性的核心。
    """
    cleaned_products = []
    if not isinstance(raw_product_list, list):
        return cleaned_products

    for product in raw_product_list:
        if not isinstance(product, dict):
            continue

        pid = product.get("publicId")
        name = product.get("name") or "未知商品"

        if not pid:
            continue

        # --- 1. 新的价格提取逻辑 (按你的优先级) ---
        price_type = "none"
        price_value = None

        if product.get("membershipPrice") is not None:
            price_type = "membershipPrice"
            price_value = product.get("membershipPrice")
        elif product.get("appPrice") is not None:
            price_type = "appPrice"
            price_value = product.get("appPrice")
        elif product.get("fromPrice") is not None:
            price_type = "fromPrice"
            price_value = product.get("fromPrice")
        elif product.get("price") is not None:
            price_type = "price"
            price_value = product.get("price")

        # --- 2. 最健壮的超市名称提取逻辑 ---
        supermarket_name = "未知超市"
        business_obj = product.get("business")
        if isinstance(business_obj, dict):
            supermarket_name = business_obj.get("name") or "未知超市"
        
        # --- 3. 组装最终的、干净的商品字典 ---
        cleaned_product = {
            "publicId": pid,
            "name": name,
            "price_type": price_type,
            "price_value": price_value,
            "supermarket": supermarket_name,
            "image": product.get("image") or "https://via.placeholder.com/150?text=No+Image",
            "unitPrice": product.get("unitPrice"),
            "description": product.get("description")
        }
        
        cleaned_products.append(cleaned_product)
            
    return cleaned_products

# ==============================================================================
# 路由 (Routes)
# ==============================================================================

@app.route("/")
def index():
    """渲染主页"""
    return render_template('index.html')

@app.route("/search")
def search_api():
    """核心的搜索API接口"""
    keyword = request.args.get("keyword")
    if not keyword:
        return jsonify({"error": "A 'keyword' query parameter is required."}), 400

    payload = create_search_payload(keyword)
    api_data = fetch_search_results(payload)

    if not api_data:
        return jsonify({"error": "Failed to fetch data from upstream API."}), 502

    raw_product_list = api_data.get("value", {}).get("data")
    if raw_product_list is None:
        return jsonify({"error": "Upstream API returned an unexpected format."}), 500

    # 使用我们的清洗函数
    final_product_list = clean_and_prepare_products(raw_product_list)

    # 存储清洗过的数据
    store_products(final_product_list, keyword)

    # 将清洗过的数据返回给前端
    return jsonify(final_product_list)

# ==============================================================================
# 程序主入口
# ==============================================================================

if __name__ == "__main__":
    setup_database()
    app.run(debug=True)