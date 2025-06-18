import sqlite3

# データベースファイルに接続（なければ新規作成される）
connection = sqlite3.connect('wiki.db')
# open() に encoding='utf-8' を追加
with open('schema.sql', encoding='utf-8') as f:
    connection.executescript(f.read())


# ↓↓↓ここから追記↓↓↓
# 追記：テストデータをデータベースに挿入する
cur = connection.cursor()

cur.execute("INSERT INTO pages (title, content) VALUES (?, ?)",
            ('ホームページ', 'これはホームページの本文です。ようこそ！')
            )

cur.execute("INSERT INTO pages (title, content) VALUES (?, ?)",
            ('使い方', 'このWikiの使い方を説明します。\n1. 新規作成\n2. 編集\n3. 削除')
            )
# ↑↑↑ここまで追記↑↑↑


# データベースへの変更を保存して、接続を閉じる
connection.commit()
connection.close()
