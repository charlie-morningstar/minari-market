-- ============================================================================
--  중고거래 플랫폼 데이터베이스 스키마
--  - 모든 조회/삽입은 파이썬 쪽에서 파라미터 바인딩(?)으로만 수행한다.
--    (문자열을 이어붙여 쿼리를 만들지 않음 → SQL Injection 원천 차단)
--  - 외래키 제약을 켜서 데이터 무결성을 보장한다.
-- ============================================================================

PRAGMA foreign_keys = ON;

-- 사용자 --------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id            TEXT PRIMARY KEY,              -- UUID(추측 불가한 식별자)
    username      TEXT NOT NULL UNIQUE,          -- 로그인 아이디(중복 불가)
    password_hash TEXT NOT NULL,                 -- bcrypt 해시(평문 저장 금지)
    bio           TEXT NOT NULL DEFAULT '',      -- 자기소개
    balance       INTEGER NOT NULL DEFAULT 0,    -- 가상 잔액(포인트)
    is_admin      INTEGER NOT NULL DEFAULT 0,    -- 관리자 여부(0/1)
    is_dormant    INTEGER NOT NULL DEFAULT 0,    -- 휴면(차단) 여부(0/1)
    report_count  INTEGER NOT NULL DEFAULT 0,    -- 누적 피신고 횟수
    failed_login  INTEGER NOT NULL DEFAULT 0,    -- 연속 로그인 실패 횟수
    lock_until    TEXT,                          -- 이 시각까지 로그인 잠금(ISO)
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 상품 ----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS products (
    id           TEXT PRIMARY KEY,
    title        TEXT NOT NULL,
    description  TEXT NOT NULL,
    price        INTEGER NOT NULL,
    seller_id    TEXT NOT NULL,
    image_path   TEXT,                           -- 대표(첫 번째) 이미지 파일명. 목록 썸네일용
    is_blocked   INTEGER NOT NULL DEFAULT 0,      -- 신고 누적으로 숨김 처리됨(0/1)
    report_count INTEGER NOT NULL DEFAULT 0,
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (seller_id) REFERENCES users(id) ON DELETE CASCADE
);

-- 상품 이미지(한 상품에 여러 장) ---------------------------------------------
-- 상세 페이지에서 화살표로 넘겨보는 갤러리에 사용한다.
CREATE TABLE IF NOT EXISTS product_images (
    id         TEXT PRIMARY KEY,
    product_id TEXT NOT NULL,
    image_path TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,        -- 표시 순서
    FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
);

-- 신고 ----------------------------------------------------------------------
-- 같은 사람이 같은 대상을 중복 신고하지 못하도록 UNIQUE 제약을 건다.
CREATE TABLE IF NOT EXISTS reports (
    id          TEXT PRIMARY KEY,
    reporter_id TEXT NOT NULL,
    target_type TEXT NOT NULL CHECK (target_type IN ('user', 'product')),
    target_id   TEXT NOT NULL,
    reason      TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (reporter_id) REFERENCES users(id) ON DELETE CASCADE,
    UNIQUE (reporter_id, target_type, target_id)
);

-- 채팅 메시지 ---------------------------------------------------------------
-- room = 'global' 이면 전체 채팅, 그 외에는 1:1 채팅방(두 유저 id 조합)
CREATE TABLE IF NOT EXISTS messages (
    id          TEXT PRIMARY KEY,
    room        TEXT NOT NULL,
    sender_id   TEXT NOT NULL,
    content     TEXT NOT NULL DEFAULT '',        -- 글 메시지(사진만 보낼 땐 빈 문자열)
    image_path  TEXT,                            -- 사진 메시지일 때 저장된 파일명
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (sender_id) REFERENCES users(id) ON DELETE CASCADE
);

-- 송금(가상 잔액 이체) 내역 -------------------------------------------------
CREATE TABLE IF NOT EXISTS transfers (
    id          TEXT PRIMARY KEY,
    sender_id   TEXT NOT NULL,
    receiver_id TEXT NOT NULL,
    amount      INTEGER NOT NULL,
    memo        TEXT NOT NULL DEFAULT '',
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (sender_id)   REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (receiver_id) REFERENCES users(id) ON DELETE CASCADE
);

-- 조회 성능용 인덱스 --------------------------------------------------------
CREATE INDEX IF NOT EXISTS idx_products_seller ON products(seller_id);
CREATE INDEX IF NOT EXISTS idx_messages_room   ON messages(room);
CREATE INDEX IF NOT EXISTS idx_reports_target  ON reports(target_type, target_id);
