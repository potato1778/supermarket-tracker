import requests
from bs4 import BeautifulSoup

# 1. 目标是网站首页
url = 'http://books.toscrape.com/'

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36'
}
response = requests.get(url, headers=headers)
response.encoding = 'utf-8'

soup = BeautifulSoup(response.text, 'html.parser')

# --- 挑战开始 ---

# 任务一: 找到所有书本的“容器”列表
# 根据你的侦察，使用 find_all 方法。
# 你需要填入正确的“标签名”和“class_”参数。
all_books = soup.find_all('article', class_='product_pod') 

# 任务二: 使用 for 循环，逐一处理每一本书
# 这个循环结构已经为你搭好
for book in all_books:
    # 在这个循环里，`book` 变量就代表着 all_books 列表中的
    # 某一个“书本容器”的代码块。
    # 所以，我们接下来的查找操作，都应该从 `book` 开始，而不是 `soup`。
    
    # 任务三: 在每个 book 容器内，找到并提取书名
    # 提示：先找到包含书名的那个元素
    title_element = book.find('h3') # 应该找什么标签？
    # 提示：然后从元素中提取书名文本或属性
    book_title = title_element.text
    
    # 任务四: 在每个 book 容器内，找到并提取价格
    # 提示：和任务三类似，先定位元素，再提取内容
    price_element = book.find('p', class_='price_color')
    book_price = price_element.text  # 提取价格文本
    
    # 任务五: 打印结果
    print(f"书名: {book_title.strip()}")
    print(f"价格: {book_price.strip()}")
    print("---")

# --- 挑战结束 ---