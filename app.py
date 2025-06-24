import sqlite3
import markdown
from flask import Flask, render_template, g, abort, request, redirect, url_for, flash
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_bcrypt import Bcrypt
import os
from werkzeug.utils import secure_filename
from flask import send_from_directory # これも追加

# --- アプリケーションの設定 ---
DATABASE = 'wiki.db'
SECRET_KEY = 'your_secret_key_here' # flashメッセージとセッション管理のために必要
UPLOAD_FOLDER = 'uploads' # アップロードフォルダの場所
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif'} # 許可する拡張子
app = Flask(__name__)
app.config.from_object(__name__) # 上記の設定をappから読み込む

# --- 拡張機能の初期化 ---
bcrypt = Bcrypt(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login' # 未ログイン時にリダイレクトする先を指定
login_manager.login_message = "このページにアクセスするにはログインが必要です。"
login_manager.login_message_category = "error"


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


# --- Userモデルクラスの定義 (Flask-Login用) ---
class User(UserMixin):
    """Flask-Loginがユーザー情報を扱うためのクラス"""
    def __init__(self, id, username, password):
        self.id = id
        self.username = username
        self.password = password


# --- ログイン管理 ---
@login_manager.user_loader
def load_user(user_id):
    """セッションからユーザー情報をロードするための関数"""
    db = get_db()
    cur = db.execute('SELECT id, username, password FROM users WHERE id = ?', (user_id,))
    user_data = cur.fetchone()
    if user_data is None:
        return None
    return User(id=user_data['id'], username=user_data['username'], password=user_data['password'])


# --- ルーティング（公開ページ） ---
@app.route('/')
def show_pages():
    """トップページ。全ページのタイトルを一覧表示する。"""
    db = get_db()
    cur = db.execute('SELECT id, title FROM pages ORDER BY id DESC')
    pages = cur.fetchall()
    return render_template('index.html', pages=pages)

@app.route('/page/<int:page_id>')
def view_page(page_id):
    db = get_db()
    cur = db.execute('SELECT id, title, content FROM pages WHERE id = ?', (page_id,))
    page = cur.fetchone()
    if page is None:
        abort(404)

    # このページに紐づくタグを取得
    cur = db.execute("""
        SELECT t.name FROM tags t JOIN page_tags pt ON t.id = pt.tag_id
        WHERE pt.page_id = ?
    """, (page_id,))
    tags = cur.fetchall()

    extensions = [
        'tables',        # 表を有効にする
        'fenced_code',   # コードブロックをきれいに表示する
        'nl2br',         # 改行をそのまま<br>タグに変換する
        'sane_lists',    # 箇条書きの挙動をより直感的にする
    ]
    # markdown関数に、extensionsリストを渡す
    content_html = markdown.markdown(page['content'], extensions=extensions)
    # pageオブジェクト、変換後のHTML、タグのリストをテンプレートに渡す
    return render_template('page.html', page=page, content_html=content_html, tags=tags)

@app.route('/search')
def search():
    """ページを検索する"""
    query = request.args.get('q', '')
    results = []
    if query:
        db = get_db()
        search_query = f'%{query}%'
        cur = db.execute(
            'SELECT id, title FROM pages WHERE title LIKE ? OR content LIKE ? ORDER BY id DESC',
            (search_query, search_query)
        )
        results = cur.fetchall()
    return render_template('search_results.html', query=query, results=results)
# app.py の中の add_page 関数を、以下の内容でまるごと置き換えてください
@app.route('/new', methods=['GET', 'POST'])
@login_required
def add_page():
    """新規ページを作成し、タグも保存する"""
    # POSTリクエスト（フォームが送信された）の場合
    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']
        tags_string = request.form['tags'] # タグ入力欄から文字列を取得

        # タイトルが空の場合はエラー
        if not title:
            flash('タイトルを入力してください。', 'error')
            # new.htmlを再表示。入力内容はそのままにしておくと親切
            return render_template('new.html', title=title, content=content, existing_tags=tags_string)

        db = get_db()
        
        # --- ページの保存 ---
        # まずページ本体を保存
        cur = db.execute(
            'INSERT INTO pages (title, content) VALUES (?, ?)',
            (title, content)
        )
        # ★保存したばかりの新しいページのIDを取得する
        new_page_id = cur.lastrowid
        
        # --- タグの保存処理 ---
        # フォームから入力されたタグを処理
        tag_names = [tag.strip() for tag in tags_string.split(',') if tag.strip()]
        for name in tag_names:
            # tagsテーブルに存在するか確認
            cur = db.execute('SELECT id FROM tags WHERE name = ?', (name,))
            tag = cur.fetchone()
            if tag:
                # 存在すればそのIDを使用
                tag_id = tag['id']
            else:
                # なければtagsテーブルに新規追加し、そのIDを取得
                cur = db.execute('INSERT INTO tags (name) VALUES (?)', (name,))
                tag_id = cur.lastrowid
            
            # page_tagsテーブルに、新しいページIDとタグIDの関連を追加
            db.execute('INSERT INTO page_tags (page_id, tag_id) VALUES (?, ?)', (new_page_id, tag_id))
        
        db.commit()
        flash('新しいページがタグと共に保存されました。', 'success')
        
        # 保存後、今作成したばかりのページにリダイレクト
        return redirect(url_for('view_page', page_id=new_page_id))
            
    # GETリクエスト（通常アクセス）の場合は、空のフォームを表示
    return render_template('new.html')

@app.route('/edit/<int:page_id>', methods=['GET', 'POST'])
@login_required
def edit_page(page_id):
    db = get_db()
    # POST（更新）処理
    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']
        tags_string = request.form['tags']

        # ... (タイトルや本文のバリデーションは省略) ...

        # データベースを更新
        db.execute('UPDATE pages SET title = ?, content = ? WHERE id = ?', (title, content, page_id))

        # --- タグの更新処理 ---
        # 1. このページに紐づく既存のタグ関連を一旦すべて削除
        db.execute('DELETE FROM page_tags WHERE page_id = ?', (page_id,))

        # 2. フォームから入力されたタグを処理
        tag_names = [tag.strip() for tag in tags_string.split(',') if tag.strip()]
        for name in tag_names:
            # tagsテーブルに存在するか確認
            cur = db.execute('SELECT id FROM tags WHERE name = ?', (name,))
            tag = cur.fetchone()
            if tag:
                tag_id = tag['id']
            else:
                # なければtagsテーブルに新規追加
                cur = db.execute('INSERT INTO tags (name) VALUES (?)', (name,))
                tag_id = cur.lastrowid

            # page_tagsテーブルに新しい関連を追加
            db.execute('INSERT INTO page_tags (page_id, tag_id) VALUES (?, ?)', (page_id, tag_id))

        db.commit()
        flash('ページが更新されました。', 'success')
        return redirect(url_for('view_page', page_id=page_id))

    # GET（表示）処理
    cur = db.execute('SELECT id, title, content FROM pages WHERE id = ?', (page_id,))
    page = cur.fetchone()
    if page is None:
        abort(404)

    # このページに紐づく既存のタグを取得
    cur = db.execute("""
        SELECT t.name FROM tags t JOIN page_tags pt ON t.id = pt.tag_id
        WHERE pt.page_id = ?
    """, (page_id,))
    existing_tags_list = [row['name'] for row in cur.fetchall()]
    existing_tags = ', '.join(existing_tags_list)

    return render_template('edit.html', page=page, existing_tags=existing_tags)
   
@app.route('/delete/<int:page_id>', methods=['POST'])
@login_required
def delete_page(page_id):
    """指定されたIDのページを削除する"""
    db = get_db()
    db.execute('DELETE FROM pages WHERE id = ?', (page_id,))
    db.commit()
    flash('ページが削除されました。', 'success')
    return redirect(url_for('show_pages'))


# --- ルーティング（認証） ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    """ログイン処理を行う"""
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        db = get_db()
        cur = db.execute('SELECT id, username, password FROM users WHERE username = ?', (username,))
        user_data = cur.fetchone()
        if user_data and bcrypt.check_password_hash(user_data['password'], password):
            user = User(id=user_data['id'], username=user_data['username'], password=user_data['password'])
            login_user(user)
            flash('ログインしました。', 'success')
            return redirect(url_for('show_pages'))
        else:
            flash('ユーザー名またはパスワードが正しくありません。', 'error')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    """ログアウト処理を行う"""
    logout_user()
    flash('ログアウトしました。', 'info')
    return redirect(url_for('show_pages'))


# --- エラーハンドリング ---
@app.errorhandler(404)
def page_not_found(error):
    """404エラーページのハンドリング"""
    return render_template('404.html'), 404

# ... page_not_found(error) の後に追加 ...

@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    """アップロードされたファイルを提供する"""
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

@app.route('/tag/<string:tag_name>')
def show_pages_by_tag(tag_name):
    """指定されたタグが付いたページを一覧表示する"""
    db = get_db()

    # タグ名からタグIDを取得
    cur = db.execute('SELECT id FROM tags WHERE name = ?', (tag_name,))
    tag = cur.fetchone()

    if tag is None:
        abort(404) # タグが存在しない場合は404

    # タグIDに紐づくページの一覧を取得
    cur = db.execute("""
        SELECT p.id, p.title FROM pages p JOIN page_tags pt ON p.id = pt.page_id
        WHERE pt.tag_id = ?
    """, (tag['id'],))
    pages = cur.fetchall()

    # 検索結果表示用のテンプレートを再利用する
    return render_template('search_results.html', query=f"タグ: {tag_name}", results=pages)

# --- 実行ブロック ---
if __name__ == '__main__':
    app.run(debug=True)