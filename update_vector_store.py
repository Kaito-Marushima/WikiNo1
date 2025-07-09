import sqlite3
import numpy as np
import faiss
import pickle
from sentence_transformers import SentenceTransformer
from datetime import datetime

# --- 既存のベクトルDBとモデルを読み込む ---
print("AIモデルと既存のベクトルDBを読み込み中...")
try:
    model = SentenceTransformer('all-MiniLM-L6-v2')
    faiss_index = faiss.read_index('wiki_faiss.index')
    with open('chunks.pkl', 'rb') as f:
        chunk_data = pickle.load(f)
except FileNotFoundError:
    print("エラー: 既存のベクトルデータベースが見つかりません。")
    print("先に `python create_vector_store.py` を実行して、初回DBを作成してください。")
    exit()
print("読み込み完了。")

# --- データベースから「未処理」のページだけを取得 ---
connection = sqlite3.connect('wiki.db')
connection.row_factory = sqlite3.Row
# vectorized_atがNULLのページ（＝まだベクトル化されていないページ）を取得
cur = connection.execute('SELECT id, title, content FROM pages WHERE vectorized_at IS NULL')
new_pages = cur.fetchall()

if not new_pages:
    print("更新対象の新規ページはありませんでした。")
    exit()

print(f"{len(new_pages)}件の新規ページを処理します...")

# --- 新しいページのチャンクを作成し、ベクトル化 ---
new_chunks = []
new_chunk_references = []
page_ids_to_update = []

for page in new_pages:
    paragraphs = page['content'].split('\n\n')
    for para in paragraphs:
        if para.strip():
            new_chunks.append(para)
            new_chunk_references.append({'page_id': page['id'], 'title': page['title']})
    page_ids_to_update.append(page['id'])

if new_chunks:
    new_chunk_embeddings = model.encode(new_chunks, convert_to_tensor=False)

    # --- 既存のベクトルDBに追加 ---
    # 新しいIDを、既存のIDの続きから割り振る
    start_id = faiss_index.ntotal
    new_ids = np.arange(start_id, start_id + len(new_chunks))

    faiss_index.add_with_ids(np.array(new_chunk_embeddings, dtype=np.float32), new_ids)

    # 参照情報も更新
    chunk_data['chunks'].extend(new_chunks)
    chunk_data['references'].extend(new_chunk_references)

    # --- 処理済みページのタイムスタンプを更新 ---
    now_str = datetime.now().isoformat()
    for page_id in page_ids_to_update:
        connection.execute('UPDATE pages SET vectorized_at = ? WHERE id = ?', (now_str, page_id))

    connection.commit()

    # --- 更新したベクトルDBを上書き保存 ---
    faiss.write_index(faiss_index, 'wiki_faiss.index')
    with open('chunks.pkl', 'wb') as f:
        pickle.dump(chunk_data, f)

    print(f"{len(new_chunks)}個の新しいチャンクをベクトルデータベースに追加しました。")

connection.close()