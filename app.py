from flask import Flask, render_template, request, jsonify
from api_communicator import *
from database_manager import setup_database, store_products

app = Flask(__name__)

@app.route("/")
def index():
    return render_template('index.html')

@app.route("/about")
def about_page():
    return "This is the About Page for our Supermarket Tracker!"

@app.route("/contact")
def contact_page():
    # 2. 不再返回字符串，而是调用 render_template 函数
    #    告诉它去渲染 'templates' 文件夹下的哪个文件
    return render_template('contact.html') # <-- 关键的改变！

@app.route("/search")
def search_api():
    #setup_database() 应该开始初始化
    keyword = request.args.get("keyword")
    if not keyword:
        # 返回一个标准的JSON错误响应，并附带400状态码
        return jsonify({"error": "A 'keyword' query parameter is required."}), 400
    
    print(f"收到搜索请求，关键词: '{keyword}'")

    payload = create_search_payload(keyword)
    api_data = fetch_search_results(payload)

    # c. 对API返回结果进行健壮性检查
    if not api_data:
        return jsonify({"error": "Failed to fetch data from the upstream API."}), 502 # 502 Bad Gateway
    
    product_list = api_data.get("value", {}).get("data")    
    store_products(product_list, keyword)  # ← 保存数据

    return jsonify(product_list)

if __name__ == "__main__":
    setup_database()  # ← 启动时初始化一次
    app.run(debug=True, use_reloader=False)
