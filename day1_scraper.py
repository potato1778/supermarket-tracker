import requests
from bs4 import BeautifulSoup

url = 'http://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html'

headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36'
}
response = requests.get(url, headers=headers)

# 检查请求是否成功
if response.status_code == 200:
    print("成功获取网页内容！")

    # --- 解决方案在这里！---
    # 在解析之前，手动设置正确的编码
    response.encoding = 'utf-8'
    # -----------------------

    soup = BeautifulSoup(response.text, 'html.parser')

    title_element = soup.find('h1')
    book_title = title_element.text
    
    price_element = soup.find('p', class_='price_color')
    book_price = price_element.text
    
    print(f"书名: {book_title.strip()}")
    print(f"价格: {book_price.strip()}")

else:
    print(f"请求失败，状态码: {response.status_code}")