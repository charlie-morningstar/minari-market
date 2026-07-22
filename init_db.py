"""
데이터베이스 초기화 + 기본 데이터 생성 스크립트.

  python init_db.py

  * schema.sql 로 테이블을 만든다.
  * 관리자 계정과 데모용 샘플 계정/상품을 생성한다.
  * 관리자 비밀번호는 .env 의 ADMIN_PASSWORD 로 지정할 수 있고,
    지정하지 않으면 아래 기본값을 쓴다(README 에 안내).
"""
import os

from app import create_app
from db import get_db, init_db
from security import hash_password, new_id

ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin1234")


def seed():
    app = create_app()
    with app.app_context():
        init_db()
        db = get_db()

        # 관리자 계정(이미 있으면 건너뜀)
        exists = db.execute(
            "SELECT 1 FROM users WHERE username = ?", (ADMIN_USERNAME,)
        ).fetchone()
        if not exists:
            db.execute(
                "INSERT INTO users (id, username, password_hash, bio, is_admin, balance) "
                "VALUES (?, ?, ?, ?, 1, ?)",
                (new_id(), ADMIN_USERNAME, hash_password(ADMIN_PASSWORD),
                 "플랫폼 관리자 계정입니다.", 100000),
            )
            print(f"[+] 관리자 계정 생성: {ADMIN_USERNAME} / {ADMIN_PASSWORD}")

        # 데모용 일반 계정 2개
        demo_ids = {}
        for uname in ("hong_gildong", "kim_cheolsu"):
            row = db.execute("SELECT id FROM users WHERE username = ?", (uname,)).fetchone()
            if row:
                demo_ids[uname] = row["id"]
                continue
            uid = new_id()
            demo_ids[uname] = uid
            db.execute(
                "INSERT INTO users (id, username, password_hash, bio, balance) "
                "VALUES (?, ?, ?, ?, ?)",
                (uid, uname, hash_password("test1234"),
                 f"{uname} 의 소개글입니다.", 50000),
            )
            print(f"[+] 데모 계정 생성: {uname} / test1234")

        # 데모용 상품
        if not db.execute("SELECT 1 FROM products LIMIT 1").fetchone():
            samples = [
                ("아이폰 13 프로 128GB 그래파이트",
                 "22년에 사서 케이스+필름 계속 끼고 썼어요.\n"
                 "- 배터리 성능 87%\n- 페이스ID/카메라 정상, 잔기스 거의 없음\n"
                 "- 공기계(약정 없음), 정상 해제 확인\n박스랑 C타입 케이블 같이 드려요.",
                 520000, "hong_gildong"),
                ("맥북 에어 M2 13인치 스페이스그레이",
                 "코딩 입문용으로 쓰던 거 판매합니다.\n"
                 "- M2 / 8GB / 256GB\n- 충전 사이클 90회, 상판 찍힘 없음\n"
                 "- 애플케어 2026-11까지 남아있어요\n충전기 정품 포함.",
                 990000, "kim_cheolsu"),
                ("갤럭시 S22 액정깨짐 (부품용)",
                 "떨어뜨려서 액정 나갔고 터치 아래쪽 안 먹어요.\n"
                 "메인보드는 살아있는 것 같습니다. 부품용/수리용으로 싸게 넘겨요.\n"
                 "개인정보 초기화 완료했고 계정 다 로그아웃했습니다.",
                 60000, "hong_gildong"),
                ("구글 AI 글라스 미개봉 (직구)",
                 "직구했다가 안 써서 판매해요. 실시간 번역이랑 길안내 되는 그 모델 맞습니다.\n"
                 "미개봉 정품이고 시리얼 확인 가능해요. 국내 A/S는 안 되는 점 참고!",
                 380000, "kim_cheolsu"),
                ("아이패드 프로 11 4세대 + 애플펜슬 2세대",
                 "필기랑 간단한 드로잉용으로 쓰던 거예요.\n"
                 "- M2 / 128GB / 와이파이 모델\n- 애플펜슬 2세대 같이 드립니다\n"
                 "- 스크래치 방지 필름 부착돼 있음",
                 780000, "hong_gildong"),
                ("한성 기계식 키보드 GK888B 적축",
                 "키캡 바꾸려고 샀다가 손에 안 맞아서 팝니다. 풀배열 적축, 무접점 아니에요.\n큰 이상 없고 청소해서 보냅니다.",
                 32000, "kim_cheolsu"),
            ]
            for title, desc, price, seller in samples:
                db.execute(
                    "INSERT INTO products (id, title, description, price, seller_id) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (new_id(), title, desc, price, demo_ids[seller]),
                )
            print(f"[+] 데모 상품 {len(samples)}건 생성")

        db.commit()
        print("[✓] 초기화 완료")


if __name__ == "__main__":
    seed()
