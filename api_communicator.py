import requests
import base64
import json

API_URL = "https://ereklamblad.se/"
HEADERS = {
    'Content-Type': 'application/json',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36',
    'origin': 'https://ereklamblad.se',
    'referer': 'https://ereklamblad.se/'
}

def create_search_payload(search_term):
    command = "offers"
    params = {
        "hideUpcoming": False,
        "pagination": {"limit": 100, "offset": 0},
        "searchTerm": search_term,
        "sort": ["score_desc"]
    }
    order_content = [command, params] 
    json_str = json.dumps(order_content, separators=(",", ":"))
    bytes_data = json_str.encode('utf-8')
    encoded_bytes = base64.b64encode(bytes_data)
    final_str = encoded_bytes.decode('utf-8')
    mydict = {"data" : [final_str]} 
    return mydict

def fetch_search_results(payload):
    """
    接收一个Payload字典，发送POST请求，并返回解析后的JSON数据。
    """
    try:
        # *** 修正点：使用关键字参数 json= 和 headers= ***
        response = requests.post(
            API_URL, 
            json=payload, 
            headers=HEADERS
        )
        # 检查请求是否成功 (例如，状态码不是 2xx 或 3xx)
        response.raise_for_status()
        
        # 解析JSON响应
        data = response.json()
        return data
        
    except requests.exceptions.RequestException as e:
        print(f"网络请求时发生错误: {e}")
        return None
    except json.JSONDecodeError:
        # 增加一个针对JSON解析失败的错误处理，让程序更健壮
        print("错误：无法将服务器的响应解析为JSON。")
        return None

# =======================================================
# =============      用例测试区      ====================
# =======================================================
if __name__ == "__main__":
    test_keyword = "ost"
    print(f"--- 正在为关键词 '{test_keyword}' 创建Payload ---")
    test_payload = create_search_payload(test_keyword)
    print("生成的Payload:", json.dumps(test_payload, indent=2))

    print(f"\n--- 正在为关键词 '{test_keyword}' 获取搜索结果 ---")
    results = fetch_search_results(test_payload)

    if results:
        print("\n成功获取到结果！")
        print("结果类型:", type(results))
        # 打印出顶级键，让我们了解返回数据的结构
        print("结果的顶级键:", results.keys()) 
        # 我们可以进一步检查 'value' 里的 'data' 是否是列表
        if 'value' in results and 'data' in results['value']:
            print(f"在 'value' -> 'data' 中找到了 {len(results['value']['data'])} 个商品。")
    else:
        print("\n获取结果失败。")