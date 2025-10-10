from api_communicator import *
from database_manager import setup_database, store_products

setup_database()

keyword = input("请输入你想搜索的打折商品 (例如 mjölk, ost, bröd)")

while  not keyword:
    print("输入值不能为空，请重新输入")
    keyword = input("请输入你想搜索的打折商品 (例如 mjölk, ost, bröd)")

print(f"正在为关键词 '{keyword}' 创建Payload...")
payload = create_search_payload(keyword)

print(f"正在为关键词 '{keyword}' 获取搜索结果...")
api_data = fetch_search_results(payload)
if api_data:
    print("成功从服务器获取到数据！")

'''print(api_data)
type(api_data)'''

merchandise = api_data.get("value", {}).get("data")
if merchandise:
    print(f"正在存储 '{keyword}' 的 {len(merchandise)} 条数据...")
    store_products(merchandise, keyword)
else:
    print(f"未搜索到'{keyword}'商品，输入有误或该商品未打折")