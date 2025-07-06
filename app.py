import os
import sqlite3
import markdown
from werkzeug.utils import secure_filename
from flask import Flask, render_template, g, abort, request, redirect, url_for, flash, send_from_directory
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_bcrypt import Bcrypt

# --- アプリケーションの設定 ---
DATABASE = 'wiki.db'
SECRET_KEY = 'your_secret_key_here'
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'txt', 'pdf', 'png', 'jpg', 'jpeg', 'gif'}
app = Flask(__name__)
app.config.from_object(__name__)

# --- 拡張機能の初期化 ---
bcrypt = Bcrypt(app)
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
login_manager.login_message = "このページにアクセスするにはログインが必要です。"
login_manager.login_message_category = "error"


# --- データベース接続の管理 ---
def connect_db():
    """データベースへの接続を返す"""
    rv = sqlite3.connect(app.config['DATABASE'])
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

@app.context_processor
def inject_permission_checker():
    return dict(
        get_page_tags=get_page_tags,
        check_permission=check_permission
    )
def get_page_tags(page_id):
    """指定されたページのタグをセットで返す"""
    db = get_db()
    cur = db.execute("SELECT t.name FROM tags t JOIN page_tags pt ON t.id = pt.tag_id WHERE pt.page_id = ?", (page_id,))
    return {row['name'] for row in cur.fetchall()}
    
def check_permission(page_tags, action='view'):
    """ユーザーが特定のページに対してアクション（閲覧/編集）を実行できるかチェックする"""
    # ログインしていない場合
    if not current_user.is_authenticated:
        return '社外公開可' in page_tags
    
    # ログインしているユーザーの役職を取得
    user_role = current_user.role
    
    # ★★★ 役職名を日本語から英語に修正 ★★★
    if user_role == 'Admin':
        return True
    if user_role == 'Customer': # 「外部」を「Customer」に変更
        return '社外公開可' in page_tags
    if user_role == 'Intern':   # 「インターン生」を「Intern」に変更
        return '本業務' not in page_tags
    if user_role == 'Member':   # 「社員」を「Member」に変更
        if action == 'edit':
            return 'インターン' not in page_tags
        return True # 社員は閲覧は基本的にすべて許可
    
    return False
class User(UserMixin):
    def __init__(self, id, username, password, role): # ★roleを追加
        self.id = id
        self.username = username
        self.password = password
        self.role = role # ★role属性をセット

# --- ログイン管理 ---
@login_manager.user_loader
def load_user(user_id):
    db = get_db()
    cur = db.execute('SELECT id, username, password, role FROM users WHERE id = ?', (user_id,)) # ★roleを取得
    user_data = cur.fetchone()
    if user_data is None:
        return None
    return User(id=user_data['id'], username=user_data['username'], password=user_data['password'], role=user_data['role']) # ★roleを渡す

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
    """個別ページ。権限をチェックし、指定されたIDのページを表示する。"""
    db = get_db()
    # ページ情報を取得（著者名なども一緒に取得）
    cur = db.execute("""
        SELECT p.id, p.title, p.content, author.username as author_name, updater.username as updater_name
        FROM pages p
        JOIN users author ON p.author_id = author.id
        LEFT JOIN users updater ON p.updated_by_id = updater.id
        WHERE p.id = ?
    """, (page_id,))
    page = cur.fetchone()

    if page is None:
        abort(404)

    # --- 権限チェック ---
    page_tags = get_page_tags(page_id)
    if not check_permission(page_tags, action='view'):
        abort(403) # 閲覧権限がなければ403エラーを返す
    # --- 権限チェックここまで ---

    # MarkdownをHTMLに変換
    extensions = ['tables', 'fenced_code', 'nl2br', 'sane_lists']
    content_html = markdown.markdown(page['content'], extensions=extensions)
    
    # テンプレートに渡すために、タグのセットをリストに変換
    tags_list = list(page_tags)

    return render_template('page.html', page=page, content_html=content_html, tags=tags_list)

@app.route('/search')
def search():
    """ページを横断検索する（キーワード、著者、複数タグ対応）"""
    query = request.args.get('q', '').strip()
    results = []
    
    if query:
        db = get_db()
        
        # クエリをカンマやスペースで分割し、空の要素を取り除く
        search_terms = [term.strip() for term in query.replace(',', ' ').split() if term.strip()]
        
        if search_terms:
            # --- タグ検索ロジック ---
            # 検索ワードがすべて存在するタグと仮定して検索を試みる
            placeholders = ', '.join('?' for _ in search_terms)
            sql_query = f"""
                SELECT p.id, p.title
                FROM pages p
                JOIN page_tags pt ON p.id = pt.page_id
                JOIN tags t ON pt.tag_id = t.id
                WHERE t.name IN ({placeholders})
                GROUP BY p.id, p.title
                HAVING COUNT(DISTINCT t.name) = ?
            """
            
            # 実行するクエリに渡す引数リスト
            params = search_terms + [len(search_terms)]
            
            cur = db.execute(sql_query, params)
            results = cur.fetchall()

            # --- 全文検索ロジック (タグ検索でヒットしなかった場合) ---
            if not results:
                search_query = f'%{query}%'
                cur = db.execute("""
                    SELECT DISTINCT p.id, p.title
                    FROM pages p
                    JOIN users author ON p.author_id = author.id
                    LEFT JOIN users updater ON p.updated_by_id = updater.id
                    LEFT JOIN page_tags pt ON p.id = pt.page_id
                    LEFT JOIN tags t ON pt.tag_id = t.id
                    WHERE p.title LIKE ? 
                       OR p.content LIKE ? 
                       OR author.username LIKE ? 
                       OR updater.username LIKE ?
                       OR t.name LIKE ?
                """, (search_query, search_query, search_query, search_query, search_query))
                results = cur.fetchall()

    return render_template('search_results.html', query=query, results=results)
    
@app.route('/tag/<string:tag_name>')
def show_pages_by_tag(tag_name):
    """指定されたタグが付いたページを一覧表示する"""
    db = get_db()
    cur = db.execute('SELECT id FROM tags WHERE name = ?', (tag_name,))
    tag = cur.fetchone()
    if tag is None:
        abort(404)
    cur = db.execute("""
        SELECT p.id, p.title FROM pages p JOIN page_tags pt ON p.id = pt.page_id
        WHERE pt.tag_id = ?
    """, (tag['id'],))
    pages = cur.fetchall()
    return render_template('search_results.html', query=f"タグ: {tag_name}", results=pages)

@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    """アップロードされたファイルを提供する"""
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)

# app.py の中の add_page 関数を、以下の内容で置き換えてください
# app.py の中の add_page 関数を、以下の内容で置き換えてください

@app.route('/new', methods=['GET', 'POST'])
@login_required
def add_page():
    # フォームの入力値を保持するために、POST時にも取得
    title = request.form.get('title', '')
    content = request.form.get('content', '')
    tags_string = request.form.get('tags', '')

    if request.method == 'POST':
        upload_file = request.files.get('upload_file')

        # --- ファイルがアップロードされた場合の処理 ---
        if upload_file and upload_file.filename != '':
            filename = secure_filename(upload_file.filename)
            file_ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
            
            upload_file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

            # 画像かそれ以外かで、挿入するMarkdownを生成
            if file_ext in app.config['ALLOWED_EXTENSIONS'] and file_ext in {'png', 'jpg', 'jpeg', 'gif'}:
                markdown_to_insert = f"![{filename}](/uploads/{filename})"
            else:
                markdown_to_insert = f"[{filename}](/uploads/{filename})"
            
            # ページを保存せず、挿入用テキストをflashメッセージでユーザーに提示
            flash(f"ファイルがアップロードされました。本文に挿入するには、次のテキストをコピーしてください: `{markdown_to_insert}`", 'info')
            
            # 入力中の内容を保持したまま、同じフォームを再表示
            return render_template('new.html', title=title, content=content, existing_tags=tags_string)

        # --- ファイルアップロードがない場合（通常の保存処理） ---
        if not title:
            flash('タイトルを入力してください。', 'error')
            return render_template('new.html', title=title, content=content, existing_tags=tags_string)

        db = get_db()
        cur = db.execute(
            'INSERT INTO pages (title, content, author_id) VALUES (?, ?, ?)',
            (title, content, current_user.id)
        )
        new_page_id = cur.lastrowid
        
        # (タグの保存処理)
        tag_names = [tag.strip() for tag in tags_string.split(',') if tag.strip()]
        for name in tag_names:
            cur = db.execute('SELECT id FROM tags WHERE name = ?', (name,))
            tag = cur.fetchone()
            if tag:
                tag_id = tag['id']
            else:
                cur = db.execute('INSERT INTO tags (name) VALUES (?)', (name,))
                tag_id = cur.lastrowid
            db.execute('INSERT INTO page_tags (page_id, tag_id) VALUES (?, ?)', (new_page_id, tag_id))
        
        db.commit()
        flash('新しいページがタグと共に保存されました。', 'success')
        return redirect(url_for('view_page', page_id=new_page_id))
            
    # GETリクエストの場合は、空のフォームを表示
    return render_template('new.html')

@app.route('/edit/<int:page_id>', methods=['GET', 'POST'])
@login_required
def edit_page(page_id):
    """既存のページを編集する。最初に編集権限をチェックする。"""
    # --- 権限チェック ---
    page_tags = get_page_tags(page_id)
    if not check_permission(page_tags, action='edit'):
        abort(403) # 編集権限がなければ403エラーを返す
    # --- 権限チェックここまで ---

    db = get_db()
    
    # POSTリクエスト（フォームが更新された）の場合
    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']
        tags_string = request.form['tags']
        upload_file = request.files.get('upload_file')

        if not title:
            flash('タイトルを入力してください。', 'error')
            # エラー時もページ情報を再取得して編集画面に戻る
            cur = db.execute('SELECT id, title, content FROM pages WHERE id = ?', (page_id,))
            page = cur.fetchone()
            return render_template('edit.html', page=page, existing_tags=tags_string)

        # (ファイルアップロード処理は省略)

        # ページの更新
        db.execute(
            'UPDATE pages SET title = ?, content = ?, updated_by_id = ? WHERE id = ?',
            (title, content, current_user.id, page_id)
        )
        
        # タグの更新
        db.execute('DELETE FROM page_tags WHERE page_id = ?', (page_id,))
        tag_names = [tag.strip() for tag in tags_string.split(',') if tag.strip()]
        for name in tag_names:
            cur = db.execute('SELECT id FROM tags WHERE name = ?', (name,))
            tag = cur.fetchone()
            if tag:
                tag_id = tag['id']
            else:
                cur = db.execute('INSERT INTO tags (name) VALUES (?)', (name,))
                tag_id = cur.lastrowid
            db.execute('INSERT INTO page_tags (page_id, tag_id) VALUES (?, ?)', (page_id, tag_id))
        
        db.commit()
        flash('ページが更新されました。', 'success')
        return redirect(url_for('view_page', page_id=page_id))
            
    # GETリクエスト（編集ページを最初に表示する）の場合
    cur = db.execute('SELECT id, title, content FROM pages WHERE id = ?', (page_id,))
    page = cur.fetchone()
    if page is None:
        abort(404)
    
    # 既存のタグをカンマ区切りの文字列として取得
    existing_tags_list = [row['name'] for row in get_page_tags(page_id)]
    existing_tags = ', '.join(existing_tags_list)
    
    return render_template('edit.html', page=page, existing_tags=existing_tags)

@app.route('/delete/<int:page_id>', methods=['POST'])
@login_required
def delete_page(page_id):
    """指定されたIDのページを削除する"""
    db = get_db()
    # 先にpage_tagsテーブルから関連データを削除
    db.execute('DELETE FROM page_tags WHERE page_id = ?', (page_id,))
    # 次にpagesテーブルから本体を削除
    db.execute('DELETE FROM pages WHERE id = ?', (page_id,))
    db.commit()
    flash('ページが削除されました。', 'success')
    return redirect(url_for('show_pages'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    """ログイン処理を行う"""
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        db = get_db()
        
        # 修正点1：データベースからroleも取得する
        cur = db.execute('SELECT id, username, password, role FROM users WHERE username = ?', (username,))
        user_data = cur.fetchone()

        if user_data and bcrypt.check_password_hash(user_data['password'], password):
            # 修正点2：取得したroleをUserオブジェクトに渡す
            user = User(id=user_data['id'], username=user_data['username'], password=user_data['password'], role=user_data['role'])
            
            login_user(user)
            flash('ログインしました。', 'success')
            next_page = request.args.get('next')
            return redirect(next_page or url_for('show_pages'))
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

@app.errorhandler(403)
def forbidden(error):
    return render_template('403.html'), 403

# --- 実行ブロック ---
if __name__ == '__main__':
    app.run(debug=True)