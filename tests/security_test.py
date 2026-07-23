"""
자동 보안/기능 점검 스크립트.

실행 방법(서버를 먼저 띄운 뒤 별도 터미널에서):
    python init_db.py           # (최초 1회) DB 초기화
    python app.py               # 1번 터미널: 서버 실행
    python tests/security_test.py   # 2번 터미널: 점검 실행

체크리스트(docs/보안_체크리스트.md)의 항목 중 자동화 가능한 것들을
실제 HTTP 요청으로 검증한다. 각 테스트는 "무엇을 막는지"를 이름으로 남겼다.
"""
import re
import io
import sys
import requests
from PIL import Image

BASE = "http://127.0.0.1:5001"
results = []


def _png(color=(80, 160, 90)):
    """테스트용 작은 PNG 이미지 한 장 생성."""
    buf = io.BytesIO()
    Image.new("RGB", (60, 60), color).save(buf, "PNG")
    buf.seek(0)
    return buf


def check(cond, msg):
    results.append((cond, msg))
    print(("[PASS]" if cond else "[FAIL]"), msg)


def csrf(session, path):
    """페이지에서 CSRF 토큰을 추출한다."""
    html = session.get(BASE + path).text
    m = re.search(r'name="csrf_token" value="([^"]+)"', html)
    return m.group(1) if m else None


def main():
    # 1. 홈 접근
    check(requests.get(BASE + "/").status_code == 200, "홈 페이지 정상 로드")

    # 2. 회원가입 → 로그인(세션 확립)
    s = requests.Session()
    s.post(BASE + "/register", data={
        "csrf_token": csrf(s, "/register"),
        "username": "tester01", "password": "abcd1234", "password2": "abcd1234",
    })
    r = s.post(BASE + "/login", data={
        "csrf_token": csrf(s, "/login"),
        "username": "tester01", "password": "abcd1234",
    }, allow_redirects=True)
    check("로그아웃" in r.text, "회원가입/로그인 후 세션 확립")

    # 3. CSRF 토큰 없는 상태 변경 요청은 거부(400)
    r = s.post(BASE + "/product/new", data={"title": "x", "description": "y", "price": "1"})
    check(r.status_code == 400, "CSRF 토큰 없는 POST 거부(400)")

    # 4. 저장형 XSS 방어: 스크립트가 그대로 실행 코드로 출력되지 않아야 함
    r = s.post(BASE + "/product/new", data={
        "csrf_token": csrf(s, "/product/new"),
        "title": "보안테스트상품", "description": "<script>alert(1)</script>", "price": "1000",
    }, allow_redirects=True)
    check("<script>alert(1)</script>" not in r.text and "&lt;script&gt;" in r.text,
          "상품 설명의 XSS 페이로드가 이스케이프됨")

    # 5. 검색어 SQL Injection 안전성(파라미터 바인딩)
    r = s.get(BASE + "/", params={"q": "' OR '1'='1"})
    check(r.status_code == 200, "SQL Injection 페이로드 검색 시 오류 없이 정상 처리")

    # 6. 입력 검증: 음수 가격 거부
    r = s.post(BASE + "/product/new", data={
        "csrf_token": csrf(s, "/product/new"),
        "title": "음수가격", "description": "d", "price": "-5",
    }, allow_redirects=True)
    check("허용 범위" in r.text, "음수 가격 입력 거부")

    # 7. 인증 통제: 비로그인 상태로 보호 페이지 접근 시 리다이렉트
    guest = requests.Session()
    r = guest.get(BASE + "/wallet", allow_redirects=False)
    check(r.status_code == 302, "비로그인 사용자의 보호 페이지 접근 차단")

    # 8. 권한 통제: 일반 사용자의 관리자 페이지 접근 403
    r = s.get(BASE + "/admin/", allow_redirects=False)
    check(r.status_code == 403, "일반 사용자의 관리자 페이지 접근 403")

    # 9. 송금: 잔액 부족 거부
    r = s.post(BASE + "/wallet/transfer", data={
        "csrf_token": csrf(s, "/wallet"),
        "to_username": "hong_gildong", "amount": "999999", "memo": "x",
    }, allow_redirects=True)
    check("잔액이 부족" in r.text, "잔액 부족 시 송금 거부")

    # 10. 송금: 충전 후 정상 이체 + 자기 자신 송금 차단
    s.post(BASE + "/wallet/charge", data={"csrf_token": csrf(s, "/wallet"), "amount": "1000"})
    r = s.post(BASE + "/wallet/transfer", data={
        "csrf_token": csrf(s, "/wallet"),
        "to_username": "hong_gildong", "amount": "300", "memo": "거래",
    }, allow_redirects=True)
    check("송금했습니다" in r.text, "정상 송금 성공")
    r = s.post(BASE + "/wallet/transfer", data={
        "csrf_token": csrf(s, "/wallet"),
        "to_username": "tester01", "amount": "100",
    }, allow_redirects=True)
    check("자기 자신" in r.text, "자기 자신에게 송금 차단")

    # 11. 채팅 사진 업로드: CSRF 토큰 없으면 거부
    r = s.post(BASE + "/chat/upload", files={"image": ("a.png", _png(), "image/png")})
    check(r.status_code == 400, "CSRF 없는 채팅 사진 업로드 거부")

    # 12. 이미지가 아닌 파일은 거부
    header_token = csrf(s, "/product/new")   # 세션 공용 CSRF 토큰
    r = s.post(BASE + "/chat/upload", headers={"X-CSRFToken": header_token},
               files={"image": ("x.png", io.BytesIO(b"not an image"), "image/png")})
    check(r.status_code == 400, "이미지가 아닌 채팅 파일 업로드 거부")

    # 13. 정상 이미지 업로드 시 안전한 UUID 파일명을 돌려준다
    r = s.post(BASE + "/chat/upload", headers={"X-CSRFToken": header_token},
               files={"image": ("a.png", _png(), "image/png")})
    good = False
    try:
        j = r.json()
        good = (r.status_code == 200 and j.get("ok")
                and bool(re.match(r"^[a-f0-9]{32}\.png$", j.get("path", ""))))
    except Exception:
        good = False
    check(good, "정상 이미지 업로드 시 UUID 파일명 반환")

    passed = sum(1 for c, _ in results if c)
    print(f"\n===== 결과: {passed}/{len(results)} 통과 =====")
    sys.exit(0 if passed == len(results) else 1)


if __name__ == "__main__":
    main()
