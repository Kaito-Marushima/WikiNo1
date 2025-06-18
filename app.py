import sqlite3
from flask import Flask, render_template, g, abort

# --- アプリケーションの設定 ---
DATABASE = 'wiki.db'
app = Flask(__name__)
app.config.from_object(__name__) # 設定をappから読み込む

# --- データベース接続の管理 ---

def connect_db():
    """データベースへの接続を返す"""
    rv = sqlite3.connect(app.config['DATABASE'])
    # 辞書形式でレコードを取得できるようにする
    rv.row_factory = sqlite3.Row
    return rv

def get_db():
    """リクエストごとにデータベース接続を取得し、なければ作成する"""
    if not hasattr(g, 'sqlite_db'):
        g.sqlite_db = connect_db()
    return g.sqlite_db

@app.teardown_appcontext
def close_db(error):
    """リクエストの終了時にデータベース接続を閉じる"""
    if hasattr(g, 'sqlite_db'):
        g.sqlite_db.close()

# --- ルーティング（URLと関数の紐付け） ---

@app.route('/')
def show_pages():
    """トップページ。全ページのタイトルを一覧表示する。"""
    db = get_db()
    # pagesテーブルからidとtitleをすべて取得
    cur = db.execute('SELECT id, title FROM pages ORDER BY id DESC')
    pages = cur.fetchall()
    # 取得したデータをindex.htmlに渡して表示
    return render_template('index.html', pages=pages)

@app.route('/page/<int:page_id>')
def view_page(page_id):
    """個別ページ。指定されたIDのページを表示する。"""
    db = get_db()
    # 指定されたidのページを取得
    cur = db.execute('SELECT title, content FROM pages WHERE id = ?', (page_id,))
    page = cur.fetchone()
    # ページが見つからなければ404エラーを返す
    if page is None:
        abort(404)
    # 取得したデータをpage.htmlに渡して表示
    return render_template('page.html', page=page)

@app.errorhandler(404)
def page_not_found(error):
    """404エラーページのハンドリング"""
    return render_template('404.html'), 404

if __name__ == '__main__':
    app.run(debug=True)