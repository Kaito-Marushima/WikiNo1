import sys
import sqlite3
from flask_bcrypt import Bcrypt

# このスクリプトは独立して実行されるため、一時的にBcryptを初期化
bcrypt = Bcrypt()

# コマンドラインからの引数が正しいかチェック
# 例: python add_user.py ユーザー名 パスワード
if len(sys.argv) != 3:
    print("使い方: python add_user.py <ユーザー名> <パスワード>")
    # sys.exit()でプログラムを終了
    sys.exit(1)

# コマンドラインからユーザー名とパスワードを取得
username = sys.argv[1]
password = sys.argv[2]

# パスワードをハッシュ化
hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')

try:
    # データベースに接続
    connection = sqlite3.connect('wiki.db')
    cur = connection.cursor()

    # 新しいユーザーをusersテーブルに挿入
    cur.execute("INSERT INTO users (username, password) VALUES (?, ?)",
                (username, hashed_password))

    # 変更を保存
    connection.commit()
    print(f"ユーザー '{username}' が正常に作成されました。")

except sqlite3.IntegrityError:
    # ユーザー名が既に存在する場合のエラー (UNIQUE制約違反)
    print(f"エラー: ユーザー名 '{username}' は既に存在します。")
    sys.exit(1)
except Exception as e:
    # その他のエラー
    print(f"エラーが発生しました: {e}")
    sys.exit(1)
finally:
    # 成功・失敗にかかわらず、必ずデータベース接続を閉じる
    if 'connection' in locals() and connection:
        connection.close()