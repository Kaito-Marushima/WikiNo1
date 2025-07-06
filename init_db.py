import sqlite3
from flask_bcrypt import Bcrypt

# このスクリプトは独立して実行されるため、一時的にBcryptを初期化
bcrypt = Bcrypt()

# データベースファイルに接続（なければ新規作成される）
connection = sqlite3.connect('wiki.db')

# schema.sqlファイルを開いて中身を読み込む
with open('schema.sql', encoding='utf-8') as f:
    connection.executescript(f.read())

# データベースへの操作を行うためのカーソルを取得
cur = connection.cursor()

# --- 初期ユーザーを追加する ---
# パスワード 'admin' をハッシュ化
hashed_password = bcrypt.generate_password_hash('admin').decode('utf-8')
# 役職(role)も一緒にINSERTする
cur.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
            ('admin', hashed_password, 'Admin')
            )

# --- テスト用のページデータを追加する ---
# 著者ID(author_id)を追加。ここでは作成したばかりのadminユーザー(ID:1)が作成したことにする
cur.execute("INSERT INTO pages (title, content, author_id) VALUES (?, ?, ?)",
            ('ホームページ', 'これはホームページの本文です。ようこそ！', 1)
            )

cur.execute("INSERT INTO pages (title, content, author_id) VALUES (?, ?, ?)",
            ('使い方', '# このWikiの使い方\n\n- ページを作成\n- ページを編集\n- タグを付ける', 1)
            )

# --- テスト用のタグと関連データを追加する ---
cur.execute("INSERT INTO tags (name) VALUES (?)", ('議事録',))
cur.execute("INSERT INTO tags (name) VALUES (?)", ('ノウハウ',))
cur.execute("INSERT INTO tags (name) VALUES (?)", ('仕様書',))

# ページ1（ホームページ）にタグ1（議事録）を紐付け
cur.execute("INSERT INTO page_tags (page_id, tag_id) VALUES (?, ?)", (1, 1))
# ページ2（使い方）にタグ2（ノウハウ）を紐付け
cur.execute("INSERT INTO page_tags (page_id, tag_id) VALUES (?, ?)", (2, 2))


# データベースへの変更を保存して、接続を閉じる
connection.commit()
connection.close()

print("テストデータと初期ユーザー入りのデータベースが作成されました。")