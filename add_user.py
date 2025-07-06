import sys
import sqlite3
from flask_bcrypt import Bcrypt

bcrypt = Bcrypt()

# 引数が4つ（ファイル名, ユーザー名, パスワード, 役職）あるかチェック
if len(sys.argv) != 4:
    print("使い方: python add_user.py <ユーザー名> <パスワード> <役職>")
    print("役職は '管理者', '社員', 'インターン生', '外部' のいずれかを指定してください。")
    sys.exit(1)

username = sys.argv[1]
password = sys.argv[2]
role = sys.argv[3]

# 指定された役職が正しいかチェック
allowed_roles = ['Admin', 'Member', 'Intern', 'Customer']
if role not in allowed_roles:
    print(f"エラー: 無効な役職です。{', '.join(allowed_roles)} のいずれかを指定してください。")
    sys.exit(1)

hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')

try:
    connection = sqlite3.connect('wiki.db')
    cur = connection.cursor()
    # roleも一緒にINSERTする
    cur.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
                (username, hashed_password, role))
    connection.commit()
    print(f"ユーザー '{username}' (役職: {role}) が正常に作成されました。")
except sqlite3.IntegrityError:
    print(f"エラー: ユーザー名 '{username}' は既に存在します。")
    sys.exit(1)
except Exception as e:
    print(f"エラーが発生しました: {e}")
    sys.exit(1)
finally:
    if 'connection' in locals() and connection:
        connection.close()