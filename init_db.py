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

# ... 初期ユーザーを追加するコードの後 ...

# ↓↓↓ここから追記↓↓↓
# 追記：テスト用のタグと関連データを追加
cur.execute("INSERT INTO tags (name) VALUES (?)", ('議事録',))
cur.execute("INSERT INTO tags (name) VALUES (?)", ('ノウハウ',))
cur.execute("INSERT INTO tags (name) VALUES (?)", ('仕様書',))

# ページ1（ホームページ）にタグ1（議事録）を紐付け
cur.execute("INSERT INTO page_tags (page_id, tag_id) VALUES (?, ?)", (1, 1))
# ページ2（使い方）にタグ2（ノウハウ）を紐付け
cur.execute("INSERT INTO page_tags (page_id, tag_id) VALUES (?, ?)", (2, 2))
# ↑↑↑ここまで追記↑↑↑
# データベースへの変更を保存して、接続を閉じる
connection.commit()
connection.close()

print("テストデータと初期ユーザー入りのデータベースが作成されました。")