import sqlite3

con = sqlite3.connect("tutorial.db")
cur = con.cursor()
'''这张表需要包含以下四个“列”(字段)：
id: 整数类型 (INTEGER)，并且是主键 (PRIMARY KEY)。主键能确保每个联系人都有一个独一无二的编号。
name: 文本类型 (TEXT)，并且不能为空 (NOT NULL)。
phone_number: 文本类型 (TEXT)。
email: 文本类型 (TEXT)。'''
cur.execute("CREATE TABLE IF NOT EXISTS contacts "
" (ID INT PRIMARY KEY, name TEXT NOT NULL, phone_number TEXT, email TEXT)")
'''cur.execute("INSERT INTO contacts (ID, name, phone_number, email) " \
"VALUES (1, '小姜', '13133556879', '123@qq.com')")'''

'''sqlinsert4 = "INSERT INTO contacts (ID, name, phone_number, email)" \
"                       VALUES (?, ?, ?, ?)"
DATA1 = [2, "小da姜", "13133556879", "123@qq.com"]
cur.execute(sqlinsert4, DATA1)
con.commit()
'''

cur.execute("SELECT * FROM contacts")
allp = cur.fetchall()
for i in allp:
    print(f"ID为:{i[0]}")
    print(f"name为:{i[1]}")
sqlselect = "SELECT * FROM contacts WHERE name = ?"
cur.execute(sqlselect, ('小姜',))
print(cur.fetchone())