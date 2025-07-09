import sqlite3
import numpy as np
import faiss
import pickle
from sentence_transformers import SentenceTransformer

print("モデルを読み込んでいます...")
# 日本語にも対応した高性能なモデルを読み込む
model = SentenceTransformer('all-MiniLM-L6-v2')
print("モデルの読み込み完了。")

# データベースから全ページのコンテンツを取得
connection = sqlite3.connect('wiki.db')
connection.row_factory = sqlite3.Row
cur = connection.execute('SELECT id, title, content FROM pages')
pages = cur.fetchall()
connection.close()

# チャンク（検索対象のテキスト断片）と参照元情報を保存するリスト
chunks = []
chunk_references = []

print(f"{len(pages)}件のページを処理中...")
for page in pages:
    # ページの内容を段落ごとに分割（簡易的なチャンキング）
    paragraphs = page['content'].split('\n\n')
    for para in paragraphs:
        if para.strip(): # 空の段落は無視
            chunks.append(para)
            chunk_references.append({'page_id': page['id'], 'title': page['title']})

print(f"{len(chunks)}個のチャンクを作成しました。ベクトルに変換します...")
# 全チャンクをベクトルに変換
chunk_embeddings = model.encode(chunks, convert_to_tensor=False)

print("ベクトルデータベースを構築中...")
# FAISSインデックスを作成
index = faiss.IndexIDMap(faiss.IndexFlatL2(chunk_embeddings.shape[1]))
index.add_with_ids(np.array(chunk_embeddings, dtype=np.float32), np.arange(len(chunks)))

# 作成したインデックスと、参照情報をファイルに保存
faiss.write_index(index, 'wiki_faiss.index')
with open('chunks.pkl', 'wb') as f:
    pickle.dump({'chunks': chunks, 'references': chunk_references}, f)

print("ベクトルデータベースの作成が完了しました。")