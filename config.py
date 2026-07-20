# 설정값 모아두는 곳 (세션키, 쿠키 옵션, 업로드 제한, 정책 숫자들).
# 비밀키처럼 민감한 건 코드에 안 박고 .env 에서 읽어옴.
# 비밀키가 깃에 올라가면 세션 위조가 가능해지니까 이건 꼭 분리해야 함.
import os
from datetime import timedelta
from dotenv import load_dotenv

# 프로젝트 루트 경로 기준으로 .env 를 읽는다.
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))


class Config:
    # --- 세션/암호화 비밀키 ---------------------------------------------------
    # 환경변수 SECRET_KEY 가 없으면 임시 랜덤값을 쓴다. 다만 이 경우 서버를
    # 재시작할 때마다 모든 세션이 풀리므로, 운영/채점 환경에서는 .env 에
    # 고정 키를 반드시 넣도록 README 에 안내했다.
    SECRET_KEY = os.environ.get("SECRET_KEY") or os.urandom(32).hex()

    # --- 데이터베이스 --------------------------------------------------------
    # 기본은 프로젝트 내 instance/market.db. 필요 시 환경변수 DATABASE_PATH 로
    # 위치를 바꿀 수 있다(자동화 테스트 등에서 임시 경로를 지정할 때 사용).
    DATABASE = os.environ.get("DATABASE_PATH") or os.path.join(BASE_DIR, "instance", "market.db")

    # --- 세션 쿠키 보안 옵션 --------------------------------------------------
    # HttpOnly : 자바스크립트(document.cookie)로 세션 쿠키를 못 읽게 → XSS 로
    #            세션 탈취되는 것을 방지
    # SameSite : 크로스 사이트 요청에 쿠키를 자동 첨부하지 않음 → CSRF 완화
    # Secure   : HTTPS 에서만 쿠키 전송. 로컬(http) 개발 시엔 꺼야 로그인이
    #            되므로 환경변수로 토글할 수 있게 했다. (운영/ngrok=https 에선 켬)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = os.environ.get("COOKIE_SECURE", "0") == "1"

    # 세션 유효기간(장시간 방치된 세션 자동 만료)
    PERMANENT_SESSION_LIFETIME = timedelta(hours=2)

    # --- 파일 업로드 제한 -----------------------------------------------------
    UPLOAD_DIR = os.path.join(BASE_DIR, "static", "uploads")
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024         # 업로드 전체 요청 상한(사진 여러 장 대비 16MB)
    ALLOWED_IMAGE_EXT = {"png", "jpg", "jpeg", "gif", "webp"}
    MAX_PRODUCT_IMAGES = 6                         # 상품 1건당 사진 최대 장수

    # --- 도메인 규칙(정책값) --------------------------------------------------
    REPORT_BLOCK_THRESHOLD = 3     # 상품이 이 횟수 이상 신고되면 자동 숨김
    REPORT_DORMANT_THRESHOLD = 5   # 유저가 이 횟수 이상 신고되면 휴면 전환
    LOGIN_MAX_FAIL = 5             # 로그인 연속 실패 허용 횟수
    LOGIN_LOCK_MINUTES = 5         # 초과 시 계정 잠금 시간(분)
    MIN_PRICE = 0                  # 상품 최소 가격
    MAX_PRICE = 100_000_000        # 상품 최대 가격(1억, 비정상 입력 차단)
