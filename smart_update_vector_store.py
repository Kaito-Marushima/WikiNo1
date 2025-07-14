import sqlite3
import numpy as np
import faiss
import pickle
from sentence_transformers import SentenceTransformer
from datetime import datetime
import os

# --- 共通の関数定義 ---

def get_db_connection():
    """データベース接続を取得する"""
    connection = sqlite3.connect('wiki.db')
    connection.row_factory = sqlite3.Row
    return connection

def create_chunks_from_pages(pages):
    """ページリストからチャンクと参照情報を作成する"""
    chunks = []
    chunk_references = []
    for page in pages:
        paragraphs = page['content'].split('\n\n')
        for para in paragraphs:
            if para.strip():
                chunks.append(para)
                chunk_references.append({'page_id': page['id'], 'title': page['title']})
    return chunks, chunk_references

# --- メインロジック ---

print("更新チェックを開始します...")
connection = get_db_connection()
cur = connection.cursor()

# 1. 既存ページで、ベクトル化された後に更新されたものはあるか？
cur.execute("SELECT 1 FROM pages WHERE vectorized_at IS NOT NULL AND updated_at > vectorized_at LIMIT 1")
is_existing_page_updated = cur.fetchone() is not None

# 2. 今日は土曜日か？ (月曜日=0, ... 土曜日=5)
is_saturday = datetime.now().weekday() == 5

# --- 実行モードを決定 ---

# 【条件A】既存ページが更新されており、かつ今日が土曜日なら「全件洗い替え」
if is_existing_page_updated and is_saturday:
    print("実行モード: 全件洗い替え（土曜日の定期メンテナンス）")
    
    model = SentenceTransformer('all-MiniLM-L6-v2')
    cur.execute('SELECT id, title, content FROM pages')
    all_pages = cur.fetchall()
    
    chunks, chunk_references = create_chunks_from_pages(all_pages)
    chunk_embeddings = model.encode(chunks, convert_to_tensor=False)
    
    index = faiss.IndexIDMap(faiss.IndexFlatL2(chunk_embeddings.shape[1]))
    index.add_with_ids(np.array(chunk_embeddings, dtype=np.float32), np.arange(len(chunks)))
    
    faiss.write_index(index, 'wiki_faiss.index')
    with open('chunks.pkl', 'wb') as f:
        pickle.dump({'chunks': chunks, 'references': chunk_references}, f)
        
    # 全ページのvectorized_atを更新
    now_str = datetime.now().isoformat()
    connection.execute("UPDATE pages SET vectorized_at = ?", (now_str,))
    connection.commit()
    print("全ページのベクトル化が完了しました。")

# 【条件B】それ以外の場合（新規ページのみ、または更新があっても平日）は「差分更新」
else:
    if is_existing_page_updated:
        print("注意: 既存ページに更新が検出されました。次回の土曜日に全件洗い替えが実行されます。")
    
    print("実行モード: 新規ページのみ差分更新")
    
    # 既存のベクトルDBがなければ初回実行を促す
    if not os.path.exists('wiki_faiss.index'):
        print("エラー: ベクトルデータベースが見つかりません。")
        print("初回は `create_vector_store.py` を実行するか、土曜日にこのスクリプトを実行してください。")
        exit()
        
    model = SentenceTransformer('all-MiniLM-L6-v2')
    faiss_index = faiss.read_index('wiki_faiss.index')
    with open('chunks.pkl', 'rb') as f:
        chunk_data = pickle.load(f)

    # 未処理の新規ページのみを取得
    cur.execute('SELECT id, title, content FROM pages WHERE vectorized_at IS NULL')
    new_pages = cur.fetchall()

    if not new_pages:
        print("更新対象の新規ページはありませんでした。")
    else:
        print(f"{len(new_pages)}件の新規ページを処理します...")
        new_chunks, new_chunk_references = create_chunks_from_pages(new_pages)
        
        if new_chunks:
            new_chunk_embeddings = model.encode(new_chunks, convert_to_tensor=False)
            
            start_id = faiss_index.ntotal
            new_ids = np.arange(start_id, start_id + len(new_chunks))
            faiss_index.add_with_ids(np.array(new_chunk_embeddings, dtype=np.float32), new_ids)
            
            chunk_data['chunks'].extend(new_chunks)
            chunk_data['references'].extend(new_chunk_references)
            
            now_str = datetime.now().isoformat()
            page_ids_to_update = [page['id'] for page in new_pages]
            for page_id in page_ids_to_update:
                connection.execute('UPDATE pages SET vectorized_at = ? WHERE id = ?', (now_str, page_id))
            
            connection.commit()
            
            faiss.write_index(faiss_index, 'wiki_faiss.index')
            with open('chunks.pkl', 'wb') as f:
                pickle.dump(chunk_data, f)
            print(f"{len(new_chunks)}個の新しいチャンクをベクトルデータベースに追加しました。")

connection.close()