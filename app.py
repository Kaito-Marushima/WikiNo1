import sqlite3
import markdown
# カンマ区切りで request を追加する
from flask import Flask, render_template, g, abort, request, redirect, url_for, flash

# --- アプリケーションの設定 ---
DATABASE = 'wiki.db'
SECRET_KEY = 'your_secret_key_here' # flashメッセージ機能のために必要
app = Flask(__name__)
app.config.from_object(__name__) # 上記の設定をappから読み込む

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
    
    # データベースから取得したMarkdown形式の本文をHTMLに変換
    content_html = markdown.markdown(page['content'])
    
    # 取得したデータと変換後のHTMLをpage.htmlに渡して表示
    return render_template('page.html', page=page, content_html=content_html)

@app.route('/new', methods=['GET', 'POST'])
def add_page():
    """新規ページを作成する"""
    # POSTリクエスト（フォームが送信された）の場合
    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']

        # タイトルか本文が空の場合はエラーメッセージを表示
        if not title or not content:
            flash('タイトルと本文の両方を入力してください。', 'error')
        else:
            db = get_db()
            db.execute(
                'INSERT INTO pages (title, content) VALUES (?, ?)',
                (title, content)
            )
            db.commit()
            flash('新しいページが保存されました。', 'success')
            # 保存後はトップページにリダイレクト
            return redirect(url_for('show_pages'))
    
    # GETリクエスト（通常アクセス）の場合は、フォームのページを表示
    return render_template('new.html')

@app.route('/edit/<int:page_id>', methods=['GET', 'POST'])
def edit_page(page_id):
    """既存のページを編集する"""
    db = get_db()
    # 編集対象のページをIDで取得
    cur = db.execute('SELECT id, title, content FROM pages WHERE id = ?', (page_id,))
    page = cur.fetchone()

    if page is None:
        abort(404)

    # POSTリクエスト（フォームが送信された）の場合
    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']

        if not title or not content:
            flash('タイトルと本文の両方を入力してください。', 'error')
        else:
            # UPDATE文でデータベースのレコードを更新
            db.execute(
                'UPDATE pages SET title = ?, content = ? WHERE id = ?',
                (title, content, page_id)
            )
            db.commit()
            flash('ページが更新されました。', 'success')
            # 更新後は、編集したページにリダイレクト
            return redirect(url_for('view_page', page_id=page_id))

    # GETリクエストの場合は、既存のデータが入った編集フォームを表示
    return render_template('edit.html', page=page)

@app.route('/delete/<int:page_id>', methods=['POST'])
def delete_page(page_id):
    """指定されたIDのページを削除する"""
    db = get_db()
    db.execute('DELETE FROM pages WHERE id = ?', (page_id,))
    db.commit()
    flash('ページが削除されました。', 'success')
    return redirect(url_for('show_pages'))
# ... delete_page() 関数の後に追加 ...

@app.route('/search')
def search():
    """ページを検索する"""
    # URLのクエリパラメータから'q'の値を取得（なければ空文字）
    query = request.args.get('q', '')
    results = []

    if query:
        db = get_db()
        # title または content に query が部分一致で含まれるページを検索
        search_query = f'%{query}%'
        cur = db.execute(
            'SELECT id, title FROM pages WHERE title LIKE ? OR content LIKE ? ORDER BY id DESC',
            (search_query, search_query)
        )
        results = cur.fetchall()

    # 検索キーワードと結果をテンプレートに渡す
    return render_template('search_results.html', query=query, results=results)

# --- エラーハンドリング ---
@app.errorhandler(404)
def page_not_found(error):
    """404エラーページのハンドリング"""
    return render_template('404.html'), 404

# --- 実行ブロック ---
if __name__ == '__main__':
    app.run(debug=True)