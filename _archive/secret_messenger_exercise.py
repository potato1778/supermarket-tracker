import json

person = {
    "name": "张三",
    "age": 25,
    "city": "北京",
    "hobbies": ["读书", "游泳"],
    "married": False
}

# 转换为JSON字符串
json_string = json.dumps(person, ensure_ascii=False, indent=2)
print("Python字典转JSON:")
print(json_string)
print(person)
import json

# 使用 json.loads() - load string

json_text = '{"name": "李四", "age": 30, "city": "上海"}'
python_obj = json.loads(json_text)
print("JSON转Python字典:")
print(python_obj)
print(f"姓名: {python_obj['name']}")
print()
