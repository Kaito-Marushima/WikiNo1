import faiss
import pickle
import numpy as np
from sentence_transformers import SentenceTransformer
import os
import sqlite3
import markdown
from werkzeug.utils import secure_filename
from flask import Flask, render_template, g, abort, request, redirect, url_for, flash, send_from_directory
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_bcrypt import Bcrypt
import openai

print("AIモデルとベクトルDBを読み込み中...")
try:
    embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
    faiss_index = faiss.read_index('wiki_faiss.index')
    with open('chunks.pkl', 'rb') as f:
        chunk_data = pickle.load(f)
    print("読み込み完了。")
except FileNotFoundError:
    print("エラー: ベクトルデータベースが見つかりません。")
    print("先に `python create_vector_store.py` を実行してください。")
    embedding_model = None
    faiss_index = None
    chunk_data = None


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

def check_permission(page_permission_level, action='view'):
    """ユーザーが特定の権限レベルのページに対してアクションを実行できるかチェックする"""
    # 役職の階層を定義（数字が小さいほど偉い）
    role_hierarchy = {'Admin': 0, 'Member': 1, 'Intern': 2, 'Customer': 3}
    
    # ページの権限レベルを定義
    permission_map = {
        '管理者のみ': 0,
        '社員以上': 1,
        'インターン生以上': 2,
        '全員に公開': 4 # ログインしていない人も含めて全員
    }

    # ページの権限レベルを取得
    required_level = permission_map.get(page_permission_level, 0) # 不明な場合は最も厳しい「管理者のみ」

    # ログインしていない場合
    if not current_user.is_authenticated:
        return required_level == 4 # 「全員に公開」のページのみ許可

    # ログインしている場合
    user_level = role_hierarchy.get(current_user.role, 4) # 不明な役職は最も権限が低い
    
    # ユーザーの役職レベルが、要求されるレベル以上（数字が同じか小さい）かチェック
    return user_level <= required_level

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
    """個別ページ。新しい権限レベルに基づいて閲覧可能かチェックする。"""
    db = get_db()
    # permission_levelも取得するようにSQLを修正
    cur = db.execute("""
        SELECT p.*, author.username as author_name, updater.username as updater_name
        FROM pages p
        JOIN users author ON p.author_id = author.id
        LEFT JOIN users updater ON p.updated_by_id = updater.id
        WHERE p.id = ?
    """, (page_id,))
    page = cur.fetchone()

    if page is None:
        abort(404)

    # --- 新しい権限チェック ---
    # ページの権限レベルを引数として渡す
    if not check_permission(page['permission_level'], action='view'):
        abort(403) # 閲覧権限がなければ403エラー

    # タグを取得する
    page_tags = get_page_tags(page_id)

    # MarkdownをHTMLに変換
    extensions = ['tables', 'fenced_code', 'nl2br', 'sane_lists']
    content_html = markdown.markdown(page['content'], extensions=extensions)
    
    return render_template('page.html', page=page, content_html=content_html, tags=list(page_tags))

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

@app.route('/new', methods=['GET', 'POST'])
@login_required
def add_page():
    """新規ページを作成し、権限レベルも保存する"""
    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']
        tags_string = request.form['tags']
        permission_level = request.form['permission_level'] # ★フォームから権限レベルを取得

        if not title:
            flash('タイトルを入力してください。', 'error')
            return render_template('new.html', title=title, content=content, existing_tags=tags_string)

        # (ファイルアップロードのロジックは省略しています)

        db = get_db()
        # ★permission_levelも一緒に保存
        cur = db.execute(
            'INSERT INTO pages (title, content, author_id, permission_level) VALUES (?, ?, ?, ?)',
            (title, content, current_user.id, permission_level)
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
        flash('新しいページが保存されました。', 'success')
        return redirect(url_for('view_page', page_id=new_page_id))
            
    return render_template('new.html')

@app.route('/edit/<int:page_id>', methods=['GET', 'POST'])
@login_required
def edit_page(page_id):
    """既存のページを編集する。最初に権限レベルで編集可能かチェックする。"""
    db = get_db()
    cur = db.execute('SELECT * FROM pages WHERE id = ?', (page_id,))
    page = cur.fetchone()

    if page is None:
        abort(404)

    # --- 新しい権限チェック ---
    if not check_permission(page['permission_level'], action='edit'):
        abort(403)

    # POSTリクエスト（フォームが更新された）の場合
    if request.method == 'POST':
        title = request.form['title']
        content = request.form['content']
        tags_string = request.form['tags']
        permission_level = request.form['permission_level'] # ★フォームから権限レベルを取得
        
        # (ファイルアップロードのロジックは省略しています)

        # ★permission_levelも一緒に更新
        db.execute(
            'UPDATE pages SET title = ?, content = ?, updated_by_id = ?, permission_level = ? WHERE id = ?',
            (title, content, current_user.id, permission_level, page_id)
        )

        # (タグの更新処理)
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
    page_tags = get_page_tags(page_id)
    existing_tags = ', '.join(sorted(list(page_tags)))
    
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

@app.route('/chat')
@login_required
def chat():
    """チャットBotページを表示する"""
    return render_template('chat.html')

from flask import Flask, render_template, g, abort, request, redirect, url_for, flash, send_from_directory, jsonify

@app.route('/ask', methods=['POST'])
@login_required
def ask():
    """RAGのベクトル検索を使って質問に回答するAPI"""
    user_message = request.json.get('message')
    if not user_message:
        return jsonify({'error': 'メッセージが空です。'}), 400

    if faiss_index is None:
        return jsonify({'response': "エラー: ベクトルデータベースが読み込まれていません。"})

    # --- 1. ベクトル検索 (Retrieval) ---
    # ユーザーの質問をベクトルに変換
    query_embedding = embedding_model.encode([user_message])
    
    # FAISSで類似度が高いチャンクを検索 (上位3件)
    D, I = faiss_index.search(np.array(query_embedding, dtype=np.float32), 3)

    # 検索結果のチャンクをコンテキストとして結合
    context_list = [f"【記事タイトル】{chunk_data['references'][i]['title']}\n【内容】\n{chunk_data['chunks'][i]}" for i in I[0]]
    context = "\n\n---\n\n".join(context_list)
    
    # (以降のプロンプト作成とLLMへの送信部分は変更なし)
    try:
        prompt = f"""
        あなたは優秀な社内アシスタントです。以下の社内Wikiの情報だけを使って、ユーザーからの質問に日本語で回答してください。
        情報が見つからない場合は、「関連情報が見つかりませんでした」と正直に答えてください。

        --- 参考情報 ---
        {context}
        ---

        質問: {user_message}
        回答:
        """
        # (デモ用にプロンプトを返す部分はそのまま)
        bot_response = f"【AIへのプロンプト（デモ）】\n{prompt}"

    except Exception as e:
        print(f"Error: {e}")
        bot_response = "AIとの通信中にエラーが発生しました。"

    return jsonify({'response': bot_response})
    
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