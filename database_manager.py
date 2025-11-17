import sqlite3

DATABASE_FILE = "search_results.db"

def setup_database():
    try:
        con = sqlite3.connect(DATABASE_FILE)
        cur = con.cursor()
        cur.execute("""
                    CREATE TABLE IF NOT EXISTS products(
                        id TEXT PRIMARY KEY,
                        product_name TEXT NOT NULL,
                        price REAL, 
                        supermarket TEXT, 
                        unit_price REAL, 
                        keyword TEXT
                    )
                """)
        con.commit()
    except sqlite3.Error as e:
        print(f"数据库错误：{e}")
    con.close()
    print(f"数据库{DATABASE_FILE}已就绪")

def store_products(product_list, keyword):
    con = sqlite3.connect(DATABASE_FILE)
    cur = con.cursor()
    cur.execute
    try:
        for item in product_list:
            id = item.get("publicId")
            name = item.get("name")
            price = item.get("price", 0.0)
            business_name = item.get("business", {}).get("name")
            unitPrice = item.get("unitPrice", 0.0)
            cur.execute("""
                INSERT OR REPLACE INTO products
                (id, product_name, price, supermarket, unit_price, keyword)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (id, name, price, business_name, unitPrice, keyword))
        con.commit()
        print(f"{len(product_list)}件关于'{keyword}'的商品已成功存入数据库。")
    except sqlite3.Error as e:
        print(f"错误：{e}")
    
if __name__ == "__main__":
    # --- 测试 setup_database ---
    print("--- 正在初始化数据库 ---")
    setup_database()
    print("初始化完成。")

    # --- 测试 store_products ---
    # 1. 创建一些假的、用于测试的商品数据
    #    这个结构需要和你API返回的商品字典结构保持一致
    fake_products = [
        {
            'publicId': 'test_id_1',
            'name': '测试牛奶A',
            'price': 10.5,
            'business': {'name': '测试超市1'},
            'unitPrice': 10.5,
            'description': '这是一个测试商品'
        },
        {
            'publicId': 'test_id_2',
            'name': '测试奶酪B',
            'price': 25.0,
            'business': {'name': '测试超市2'},
            'unitPrice': 50.0,
            'description': '这是另一个测试商品'
        },
        {
            'publicId': 'test_id_1', # 注意！这是一个重复的ID
            'name': '测试牛奶A-新价格',
            'price': 9.9, # 价格更新了
            'business': {'name': '测试超市1'},
            'unitPrice': 9.9,
            'description': '这是一个更新后的测试商品'
        }
    ]
    test_keyword = "测试"

    print(f"\n--- 正在存储 '{test_keyword}' 的 {len(fake_products)} 条假数据 ---")
    
    # 2. 调用你的函数来存储这些假数据
    store_products(fake_products, test_keyword)

    print("\n存储测试完成。请使用DB Browser for SQLite检查 'search_results.db'。")
    print("你应该会看到两条记录（test_id_1的数据被更新了），并且keyword都是'测试'。")