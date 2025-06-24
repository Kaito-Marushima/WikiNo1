-- 古いテーブルがあれば削除する
DROP TABLE IF EXISTS pages;

-- 新しいテーブルを作成する
CREATE TABLE pages (
    id INTEGER PRIMARY KEY AUTOINCREMENT, -- 記事ごとに自動で割り振られる番号
    title TEXT UNIQUE NOT NULL,           -- 記事のタイトル（重複は許可しない）
    content TEXT NOT NULL,                -- 記事の本文
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP -- 作成日時
);
-- ... pagesテーブルの定義の後 ...

-- ユーザー情報を保存するテーブル
CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password TEXT NOT NULL
);

-- ... usersテーブルの定義の後 ...

-- タグを保存するテーブル
CREATE TABLE tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL
);

-- ページとタグの関連を保存する中間テーブル
CREATE TABLE page_tags (
    page_id INTEGER NOT NULL,
    tag_id INTEGER NOT NULL,
    FOREIGN KEY (page_id) REFERENCES pages (id),
    FOREIGN KEY (tag_id) REFERENCES tags (id),
    PRIMARY KEY (page_id, tag_id)
);