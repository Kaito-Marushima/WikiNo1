import sqlite3
from flask_bcrypt import Bcrypt

# データベースファイルに接続（なければ新規作成される）
connection = sqlite3.connect('wiki.db')

# schema.sqlファイルを開いて中身を読み込む
with open('schema.sql', encoding='utf-8') as f:
    connection.executescript(f.read())

# データベースへの操作を行うためのカーソルを取得
cur = connection.cursor()

# テストデータをデータベースに挿入する
cur.execute("INSERT INTO pages (title, content) VALUES (?, ?)",
            ('ホームページ', 'これはホームページの本文です。ようこそ！')
            )

cur.execute("INSERT INTO pages (title, content) VALUES (?, ?)",
            ('使い方', 'このWikiの使い方を説明します。\n1. 新規作成\n2. 編集\n3. 削除')
            )

# 初期ユーザーを追加する
# Bcryptのインスタンスを一時的に作成
bcrypt = Bcrypt()

# パスワード 'admin' をハッシュ化
hashed_password = bcrypt.generate_password_hash('admin').decode('utf-8')

cur.execute("INSERT INTO users (username, password) VALUES (?, ?)",
            ('admin', hashed_password)
            )

# データベースへの変更を保存して、接続を閉じる
connection.commit()
connection.close()

print("テストデータと初期ユーザー入りのデータベースが作成されました。")