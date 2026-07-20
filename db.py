# DB 다루는 부분.
# 규칙 딱 두 개만 지키자:
#  - 쿼리에 값 넣을 땐 무조건 ? 로. f-string 으로 SQL 만들지 말 것 (인젝션 방지).
#  - 커넥션은 요청 하나당 하나 쓰고, 끝나면 닫는다.
import sqlite3
import os
from flask import g, current_app


def get_db() -> sqlite3.Connection:
    """현재 요청에서 쓸 DB 커넥션을 반환(없으면 새로 연다)."""
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DATABASE"])
        # row 를 dict 처럼 컬럼명으로 접근할 수 있게 한다.
        g.db.row_factory = sqlite3.Row
        # 외래키 제약을 커넥션마다 활성화(SQLite 는 기본 off)
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(exc=None):
    """요청 종료 시 커넥션 정리(app.teardown 에 등록)."""
    db = g.pop("db", None)
    if db is not None:
        db.close()


def query(sql: str, params: tuple = (), one: bool = False):
    """SELECT 실행 헬퍼. one=True 면 단일 row 반환."""
    cur = get_db().execute(sql, params)
    rows = cur.fetchall()
    cur.close()
    return (rows[0] if rows else None) if one else rows


def execute(sql: str, params: tuple = ()):
    """INSERT/UPDATE/DELETE 실행 후 커밋."""
    db = get_db()
    cur = db.execute(sql, params)
    db.commit()
    lastrow = cur.lastrowid
    cur.close()
    return lastrow


def init_db():
    """schema.sql 을 실행해 테이블을 생성한다."""
    os.makedirs(os.path.dirname(current_app.config["DATABASE"]), exist_ok=True)
    with current_app.open_resource("schema.sql", mode="r") as f:
        get_db().executescript(f.read())
    get_db().commit()
