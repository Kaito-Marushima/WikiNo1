import sys
import sqlite3

# コマンドラインからの引数が正しいかチェック
# 例: python delete_user.py ユーザー名
if len(sys.argv) != 2:
    print("使い方: python delete_user.py <削除するユーザー名>")
    sys.exit(1)

# コマンドラインから削除するユーザー名を取得
username_to_delete = sys.argv[1]

#【安全装置】'admin'ユーザーは削除できないようにする
if username_to_delete == 'admin':
    print("エラー: 'admin'ユーザーは削除できません。")
    sys.exit(1)

try:
    # データベースに接続
    connection = sqlite3.connect('wiki.db')
    cur = connection.cursor()

    # 削除対象のユーザーが存在するか確認
    cur.execute("SELECT id FROM users WHERE username = ?", (username_to_delete,))
    user_exists = cur.fetchone()

    if user_exists:
        # ユーザーが存在すれば、削除を実行
        cur.execute("DELETE FROM users WHERE username = ?", (username_to_delete,))
        # 変更を保存
        connection.commit()
        print(f"ユーザー '{username_to_delete}' が正常に削除されました。")
    else:
        # ユーザーが存在しない場合
        print(f"エラー: ユーザー名 '{username_to_delete}' は存在しません。")

except Exception as e:
    # その他のエラー
    print(f"エラーが発生しました: {e}")
    sys.exit(1)
finally:
    # 成功・失敗にかかわらず、必ずデータベース接続を閉じる
    if 'connection' in locals() and connection:
        connection.close()