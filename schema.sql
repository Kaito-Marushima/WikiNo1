-- もし既存のテーブルがあれば、安全に削除する
-- 外部キー制約を考慮し、参照しているテーブル（page_tags）から先に削除する
DROP TABLE IF EXISTS page_tags;
DROP TABLE IF EXISTS pages;
DROP TABLE IF EXISTS tags;
DROP TABLE IF EXISTS users;


-- ユーザー情報を保存するテーブル
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL,
    role TEXT NOT NULL
);


-- タグを保存するテーブル
CREATE TABLE tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL
);

-- pagesテーブルの定義を変更
CREATE TABLE pages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT UNIQUE NOT NULL,
    content TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    author_id INTEGER NOT NULL,
    updated_by_id INTEGER,
    permission_level TEXT NOT NULL DEFAULT '社員以上', -- ★これを追加
    FOREIGN KEY (author_id) REFERENCES users (id),
    FOREIGN KEY (updated_by_id) REFERENCES users (id)
);

-- ページとタグの関連を保存する中間テーブル
CREATE TABLE page_tags (
    page_id INTEGER NOT NULL,
    tag_id INTEGER NOT NULL,
    -- 外部キー制約
    FOREIGN KEY (page_id) REFERENCES pages (id),
    FOREIGN KEY (tag_id) REFERENCES tags (id),
    -- 複合主キー：同じページに同じタグが複数付かないようにする
    PRIMARY KEY (page_id, tag_id)
);