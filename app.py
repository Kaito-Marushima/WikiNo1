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
    """個別ページ。指定されたIDのページを表示する。"""
    db = get_db()
    cur = db.execute('SELECT title, content FROM pages WHERE id = ?', (page_id,))
    page = cur.fetchone()
    if page is None:
        abort(404)
    content_html = markdown.markdown(page['content'])
    return render_template('page.html', page=page, content_html=content_html)

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
    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content'] # まずフォームから送られた本文を取得
        upload_file = request.files['upload_file'] # アップロードされたファイルを取得

        # タイトルが空の場合はエラー
        if not title:
            flash('タイトルを入力してください。', 'error')
            # new.htmlを再表示するが、入力内容はそのままにしておくと親切
            return render_template('new.html', title=title, content=content)

        # ファイルが選択されていれば、保存処理を行う
        if upload_file and upload_file.filename != '':
            # ファイル名を安全なものに変換（セキュリティ対策）
            filename = secure_filename(upload_file.filename)
            # ファイルの保存先パスを作成
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            # ファイルを保存
            upload_file.save(file_path)
            
            # 本文(content)の末尾に、アップロードしたファイルへのMarkdownリンクを自動で追記
            content += f"\n\n添付ファイル: [{filename}](/uploads/{filename})"
            flash('ファイルがアップロードされ、リンクが本文に追加されました。', 'info')

        db = get_db()
        # リンクが追記されたかもしれないcontentをデータベースに保存
        db.execute(
            'INSERT INTO pages (title, content) VALUES (?, ?)',
            (title, content)
        )
        db.commit()
        flash('新しいページが保存されました。', 'success')
        
        # 保存後、今作成したばかりのページに直接移動する
        cur = db.execute('SELECT last_insert_rowid()')
        new_page_id = cur.fetchone()[0]
        return redirect(url_for('view_page', page_id=new_page_id))
            
    # GETリクエストの場合は、空のフォームを表示
    return render_template('new.html')
# app.py の中の edit_page 関数も、以下の内容でまるごと置き換えてください

@app.route('/edit/<int:page_id>', methods=['GET', 'POST'])
@login_required
def edit_page(page_id):
    db = get_db()
    cur = db.execute('SELECT id, title, content FROM pages WHERE id = ?', (page_id,))
    page = cur.fetchone()
    if page is None:
        abort(404)
        
    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content'] # フォームから送られた本文を取得
        upload_file = request.files['upload_file'] # アップロードされたファイルを取得

        if not title:
            flash('タイトルを入力してください。', 'error')
            return render_template('edit.html', page=page)

        # ファイルが選択された場合の処理
        if upload_file and upload_file.filename != '':
            filename = secure_filename(upload_file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            upload_file.save(file_path)
            # 本文(content)の末尾に、アップロードしたファイルへのMarkdownリンクを自動で追記
            content += f"\n\n添付ファイル: [{filename}](/uploads/{filename})"
            flash('ファイルがアップロードされ、リンクが本文に追加されました。', 'info')

        # リンクが追記されたかもしれないcontentでデータベースを更新
        db.execute(
            'UPDATE pages SET title = ?, content = ? WHERE id = ?',
            (title, content, page_id)
        )
        db.commit()
        flash('ページが更新されました。', 'success')
        return redirect(url_for('view_page', page_id=page_id))
        
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

# --- 実行ブロック ---
if __name__ == '__main__':
    app.run(debug=True)