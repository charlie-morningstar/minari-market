# 보안 관련해서 여기저기서 쓰는 함수들 모아둔 곳.
# 해시 / 입력 검증 / 로그인·권한 체크 / 업로드 검사.
# 기능 파일들이 이걸 import 해서 씀. 한 곳에 몰아둬야 빠뜨릴 확률이 준다.
import re
import uuid
import functools
from datetime import datetime, timedelta

import bcrypt
from flask import session, redirect, url_for, flash, abort, current_app

from db import query


# ---------------------------------------------------------------------------
# 1) 비밀번호 해시 (평문 저장 금지)
# ---------------------------------------------------------------------------
def hash_password(plain: str) -> str:
    """bcrypt 로 비밀번호를 해시한다. salt 는 bcrypt 가 자동 생성/포함한다."""
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """평문과 저장된 해시를 안전하게 비교(타이밍 공격에 강한 내부 비교)."""
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except ValueError:
        # 해시 형식이 깨진 경우에도 예외를 흘리지 않고 실패로 처리
        return False


# ---------------------------------------------------------------------------
# 2) 입력값 검증 (화이트리스트 방식)
#    - "허용되는 문자만 통과"시키는 방식이 "위험한 문자만 거르는" 것보다 안전
# ---------------------------------------------------------------------------
USERNAME_RE = re.compile(r"^[A-Za-z0-9_]{4,20}$")   # 영문/숫자/밑줄, 4~20자

def validate_username(username: str):
    """아이디 규칙 검증. 통과 못 하면 사유 문자열을, 통과하면 None 을 반환."""
    if not username:
        return "아이디를 입력해 주세요."
    if not USERNAME_RE.match(username):
        return "아이디는 영문/숫자/밑줄(_) 4~20자여야 합니다."
    return None


def validate_password(password: str):
    """비밀번호 규칙 검증(길이 + 문자 종류 조합)."""
    if not password or len(password) < 8 or len(password) > 64:
        return "비밀번호는 8자 이상 64자 이하여야 합니다."
    # 영문/숫자를 각각 하나 이상 포함하도록 요구(단순 숫자·단순 문자 방지)
    if not (re.search(r"[A-Za-z]", password) and re.search(r"[0-9]", password)):
        return "비밀번호는 영문과 숫자를 모두 포함해야 합니다."
    return None


def clean_text(value: str, max_len: int) -> str:
    """
    일반 텍스트 입력 정리:
      * 앞뒤 공백 제거
      * 최대 길이 초과 시 잘라냄(과도한 입력으로 인한 저장/표시 문제 방지)
    실제 XSS 방어는 템플릿의 자동 이스케이프(Jinja2)가 담당하므로 여기서는
    태그를 억지로 제거하지 않는다. (표시 시점에 안전하게 처리)
    """
    if value is None:
        return ""
    return value.strip()[:max_len]


# ---------------------------------------------------------------------------
# 3) 로그인/권한 데코레이터
# ---------------------------------------------------------------------------
def current_user():
    """세션의 user_id 로 현재 로그인 사용자 row 를 조회(없으면 None)."""
    uid = session.get("user_id")
    if not uid:
        return None
    return query("SELECT * FROM users WHERE id = ?", (uid,), one=True)


def login_required(view):
    """로그인하지 않은 요청은 로그인 페이지로 보낸다."""
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        user = current_user()
        if user is None:
            flash("로그인이 필요합니다.")
            return redirect(url_for("auth.login"))
        # 휴면(차단) 계정은 즉시 로그아웃 처리
        if user["is_dormant"]:
            session.clear()
            flash("신고 누적으로 휴면 처리된 계정입니다. 관리자에게 문의하세요.")
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    """관리자 권한이 없는 접근은 403 으로 차단(권한 상승 방지)."""
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        user = current_user()
        if user is None:
            return redirect(url_for("auth.login"))
        if not user["is_admin"]:
            abort(403)
        return view(*args, **kwargs)
    return wrapped


# ---------------------------------------------------------------------------
# 4) 로그인 실패 잠금 (무차별 대입 방지)
# ---------------------------------------------------------------------------
def is_locked(user_row) -> bool:
    """계정이 현재 잠금 상태인지 확인."""
    lock_until = user_row["lock_until"]
    if not lock_until:
        return False
    return datetime.fromisoformat(lock_until) > datetime.now()


def lock_duration_left(user_row) -> int:
    """남은 잠금 시간(분, 올림)."""
    lock_until = user_row["lock_until"]
    if not lock_until:
        return 0
    delta = datetime.fromisoformat(lock_until) - datetime.now()
    return max(0, int(delta.total_seconds() // 60) + 1)


def next_lock_time() -> str:
    """설정된 잠금 시간만큼 뒤의 시각(ISO 문자열)."""
    minutes = current_app.config["LOGIN_LOCK_MINUTES"]
    return (datetime.now() + timedelta(minutes=minutes)).isoformat()


# ---------------------------------------------------------------------------
# 5) 업로드 이미지 검증 (악성 파일 업로드 방지)
# ---------------------------------------------------------------------------
def safe_image_save(file_storage) -> str | None:
    """
    업로드된 이미지를 검증 후 저장하고, 저장된 '파일명'을 반환한다.
    검증에 실패하면 None.

    방어 포인트:
      * 확장자 화이트리스트 검사
      * Pillow 로 실제 이미지인지 검증(확장자만 이미지인 위장 파일 차단)
      * 파일명을 UUID 로 새로 생성 → 경로 조작(../) / 파일명 기반 공격 차단
    """
    from PIL import Image  # 지연 import (미설치 환경에서도 나머지 기능 동작)

    if file_storage is None or file_storage.filename == "":
        return None

    ext = file_storage.filename.rsplit(".", 1)[-1].lower() if "." in file_storage.filename else ""
    if ext not in current_app.config["ALLOWED_IMAGE_EXT"]:
        return None

    # 실제 이미지인지 검증
    try:
        image = Image.open(file_storage.stream)
        image.verify()                 # 손상/위장 파일이면 예외 발생
    except Exception:
        return None

    file_storage.stream.seek(0)        # verify 후 스트림 위치 되돌리기
    new_name = f"{uuid.uuid4().hex}.{ext}"
    save_path = f"{current_app.config['UPLOAD_DIR']}/{new_name}"
    file_storage.save(save_path)
    return new_name


# 저장되는 이미지 파일명 형식: <uuid 32자리>.<확장자>
STORED_IMAGE_RE = re.compile(r"^[a-f0-9]{32}\.(png|jpg|jpeg|gif|webp)$")

def is_valid_stored_image(name: str) -> bool:
    """
    업로드 엔드포인트가 돌려준 '우리가 저장한 파일명'이 맞는지 검증한다.
    채팅 사진 전송 시, 클라이언트가 임의 경로(../../etc/passwd 등)를 넣는 것을
    막기 위해 형식을 엄격히 검사한다.
    """
    return bool(name and STORED_IMAGE_RE.match(name))


def new_id() -> str:
    """추측 불가능한 UUID 기반 식별자 생성."""
    return uuid.uuid4().hex
