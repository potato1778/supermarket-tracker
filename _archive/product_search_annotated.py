# ==============================================================================
# 模块导入区 (程序的“工具箱”)
# ==============================================================================

# 导入 requests 库。这是我们的“电话机”，专门用来和网络上的API(服务器)进行对话。
import requests

# 导入 json 库。这是我们的“翻译器”，能把服务器返回的JSON“电报码”翻译成Python能懂的字典和列表。
import json

# 导入 base64 库。这是我们的“加密信封”，能把我们的指令打包成一种特殊的文本格式，让服务器能安全地接收。
import base64

# 导入 sqlite3 库。这是我们的“本地仓库管理员”，负责创建数据库文件、建立货架(表)、存放货物(数据)。
import sqlite3

# ==============================================================================
# 全局配置区 (程序的“常量设定”)
# ==============================================================================

# API_URL: 我们要对话的服务器的“电话号码”。我们所有的请求都发到这个地址。
API_URL = "https://ereklamblad.se/"

# HEADERS: 我们打电话时的“身份证明”。
# 'User-Agent' 告诉服务器：“你好，我是一个Chrome浏览器”，这能避免被一些简单的反爬虫机制拦住。
# 'origin' 和 'referer' 进一步模仿了真实浏览器的行为，告诉服务器我们是从哪个页面跳转过来的。
HEADERS = {
    'Content-Type': 'application/json',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36',
    'origin': 'https://ereklamblad.se',
    'referer': 'https://ereklamblad.se/'
}

# DATABASE_FILE: 我们本地仓库(数据库)的文件名。所有数据都会存放在这个文件里。
DATABASE_FILE = "search_results.db"

# ==============================================================================
# 辅助函数区 (可重用的“工具方法”)
# ==============================================================================

def create_base64_payload(command, params):
    """
    这个函数是我们的“打包专家”。
    它接收一个指令(command)和一个参数(params)，然后生成服务器能看懂的最终请求体(Payload)。
    """
    # 步骤1: 将指令和参数打包成一个Python列表。这是我们和服务器约定的格式。
    order_content = [command, params]
    
    # 步骤2: 使用json.dumps()，将Python列表“序列化”成一个紧凑的JSON字符串。
    # 比如：["offers", {"searchTerm":"mjölk"}] -> '["offers",{"searchTerm":"mjölk"}]'
    #第一个参数: 项目之间的分隔符(逗号后面)
    #第二个参数: 键值对之间的分隔符(冒号后面)
    json_string = json.dumps(order_content, separators=(',', ':'))
    
    # 步骤3: 将JSON字符串用.encode('utf-8')转换成“字节(bytes)”。
    # 因为计算机在底层处理和传输数据时，用的都是字节，而不是我们看到的字符。
    base64_bytes = base64.b64encode(json_string.encode('utf-8'))
    
    # 步骤4: 将编码后的字节，用.decode('utf-8')再转换回我们能看的普通字符串。
    # 这样我们才能把它放进最终的JSON Payload里。
    base64_string = base64_bytes.decode('utf-8')
    
    # 步骤5: 构建最终的、要发送给服务器的字典。
    # 服务器要求格式是: {"data": [我们打包好的字符串]}
    '''简单记忆:
    字符串 → 编码 → 字节 → (这个编码只接受字节)Base64编码 → 字节 → 解码 → 字符串
    进去要编码,出来要解码,保证首尾都是字符串!'''
    return {"data": [base64_string]}


def setup_database():
    """
    这个函数是我们的“仓库建设者”。
    它负责在程序开始时，确保数据库文件和数据表都已经准备就绪。
    """
    # "with"语句是一个安全锁：它能保证无论发生什么，数据库连接最后都会被关闭。
    with sqlite3.connect(DATABASE_FILE) as conn:
        cursor = conn.cursor() # 获取“遥控器”
        
        # "CREATE TABLE IF NOT EXISTS" 是一句很安全的SQL命令。
        # 如果 "products" 表不存在，就创建它。如果已经存在，就什么也不做。
        # 这保证了我们的脚本可以反复运行而不会报错。
        # TEXT, REAL, INTEGER 是SQL里的数据类型，分别对应文本、浮点数、整数。
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS products (
                id TEXT PRIMARY KEY, product_name TEXT NOT NULL, price REAL,
                supermarket TEXT, unit_price REAL, valid_from TEXT, 
                valid_to TEXT, image_url TEXT, description TEXT,
                keyword TEXT, scraped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
    print(f"数据库 '{DATABASE_FILE}' 已就绪。")


def parse_and_store_data(response_json, db_connection, keyword):
    """
    这个函数是我们的“货物管理员”。
    它负责解析服务器返回的JSON数据，并将有用的信息存入数据库。
    """
    # 步骤1: 安全检查。先确认服务器返回的数据结构是不是我们预期的样子。
    # 我们预期 'value' 字段是一个字典，且里面包含 'data' 字段。
    value_dict = response_json.get('value')
    if not isinstance(value_dict, dict) or 'data' not in value_dict:
        print("错误：响应的 'value' 字段不是字典或其中缺少 'data' 键。")
        return # 如果格式不对，直接退出函数，避免程序崩溃。

    # 步骤2: 从正确的路径取出商品列表。
    offers_to_process = value_dict['data']

    cursor = db_connection.cursor()
    products_added = 0
    
    # 步骤3: 遍历商品列表。就像我们练习时遍历用户列表一样。
    for offer in offers_to_process:
        # 步骤4: 从每个商品字典(offer)中，安全地提取我们需要的信息。
        # .get() 方法比直接用 a['b'] 更安全，如果键不存在，它会返回None而不是报错。
        product_id, name, price = offer.get('publicId'), offer.get('name'), offer.get('price')
        
        # 步骤5: 又一次安全检查。如果连id和名字都没有，这条数据就是无用的。
        #字符串空为false 有内容为True
        if not all([product_id, name]): continue
        
        # 'business' 键下面又是一个字典，所以我们链式调用 .get() 来安全地获取超市名。
        supermarket = offer.get('business', {}).get('name')
        
        # ... 提取其他信息 ...
        unit_price = offer.get('unitPrice')
        
        # 步骤6: 使用 "INSERT OR REPLACE" 这个强大的SQL命令。
        # 如果数据库里没有这个id，就插入新数据。
        # 如果已经有这个id了，就用新数据覆盖掉旧数据。
        # 这让我们每次运行脚本都能获取到最新的价格，非常方便。
        # '?' 是占位符，用来安全地传递数据，防止SQL注入。
        cursor.execute('''
            INSERT OR REPLACE INTO products (
                id, product_name, price, supermarket, unit_price, keyword
            ) VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            product_id, name, float(price) if price else None, supermarket,
            float(unit_price) if unit_price else None, keyword
        ))
        products_added += 1

    # 步骤7: 所有数据都准备好后，用 .commit() 一次性把所有更改“保存”到数据库文件里。
    db_connection.commit()
    print(f"\n胜利！ {products_added} 件关于 '{keyword}' 的商品已成功存入数据库。")

# ==============================================================================
# 主执行区 (程序的“启动开关”)
# ==============================================================================

# 这行代码是一个Python的“规矩”。
# 意思是：只有当这个文件被直接运行时(而不是被其他文件导入时)，才执行下面的代码。
# 这让我们的脚本既能独立工作，又能安全地被其他程序当作工具库使用。
if __name__ == "__main__":
    
    # 第一步：准备好仓库。
    setup_database()

    # 第二步：询问用户想要什么。
    search_term = input("请输入你想搜索的打折商品 (例如 mjölk, ost, bröd): ")

    # 如果用户真的输入了东西...
    if search_term:
        
        # 第三步：把用户的请求，打包成服务器能听懂的“订单”。
        search_params = {
            "hideUpcoming": False,
            "pagination": {"limit": 100, "offset": 0},
            "searchTerm": search_term,
            "sort": ["score_desc"]
        }
        payload = create_base64_payload("offers", search_params)
        
        print(f"\n正在搜索 '{search_term}'...")
        
        # 第四步：启动“永不崩溃”模式。
        # try...except 就像一个安全网，即使中间发生任何错误（网络断了、服务器崩了），
        # 程序也不会直接闪退，而是会执行 except 里的代码，然后优雅地结束。
        try:
            # 第五步：发送请求，并获取回复。
            response = requests.post(API_URL, headers=HEADERS, json=payload)
            response.raise_for_status() # 这行代码会自动检查回复是不是成功(200)，如果不是就主动报错。

            # 第六步：解析回复，得到Python字典。
            response_json = json.loads(response.text.strip())
            
            # 第七步：连接仓库，并把解析好的数据交给“货物管理员”去处理。
            with sqlite3.connect(DATABASE_FILE) as conn:
                parse_and_store_data(response_json, conn, search_term)

        except Exception as e:
            # 如果 try 块里的任何一步出错了，程序就会跳到这里。
            print(f"程序执行出错: {e}")