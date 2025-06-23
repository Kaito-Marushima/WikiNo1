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