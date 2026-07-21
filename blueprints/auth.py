"""
회원 관리: 회원가입 / 로그인 / 로그아웃 / 마이페이지 / 사용자 프로필 조회.
"""
from flask import (
    Blueprint, render_template, request, redirect, url_for, flash, session, abort
)

from db import query, execute
from extensions import limiter
from security import (
    hash_password, verify_password, validate_username, validate_password,
    clean_text, current_user, login_required, is_locked, lock_duration_left,
    next_lock_time, new_id,
)

bp = Blueprint("auth", __name__)


@bp.route("/register", methods=["GET", "POST"])
@limiter.limit("10 per hour")   # 자동 가입 봇 완화
def register():
    if current_user():
        return redirect(url_for("products.index"))

    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        password2 = request.form.get("password2", "")

        # 1) 형식 검증
        err = validate_username(username) or validate_password(password)
        if err:
            flash(err)
            return render_template("register.html", username=username)
        if password != password2:
            flash("비밀번호 확인이 일치하지 않습니다.")
            return render_template("register.html", username=username)

        # 2) 아이디 중복 검사
        if query("SELECT 1 FROM users WHERE username = ?", (username,), one=True):
            flash("이미 사용 중인 아이디입니다.")
            return render_template("register.html", username=username)

        # 3) 저장(비밀번호는 해시로만 저장)
        execute(
            "INSERT INTO users (id, username, password_hash) VALUES (?, ?, ?)",
            (new_id(), username, hash_password(password)),
        )
        flash("회원가입이 완료되었습니다. 로그인해 주세요.")
        return redirect(url_for("auth.login"))

    return render_template("register.html")


@bp.route("/login", methods=["GET", "POST"])
@limiter.limit("20 per hour")   # 무차별 대입 완화(계정 잠금과 별개의 2차 방어선)
def login():
    if current_user():
        return redirect(url_for("products.index"))

    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")

        user = query("SELECT * FROM users WHERE username = ?", (username,), one=True)

        # 계정 잠금 상태면 우선 차단
        if user and is_locked(user):
            flash(f"로그인 시도가 많아 계정이 잠겼습니다. {lock_duration_left(user)}분 뒤 다시 시도하세요.")
            return render_template("login.html", username=username)

        # 아이디/비번 검증.
        # 주의: "아이디가 없음"과 "비번 틀림"을 구분해 알려주지 않는다.
        #       (계정 존재 여부가 새어나가면 공격자가 유효 아이디를 수집할 수 있음)
        if user is None or not verify_password(password, user["password_hash"]):
            if user is not None:
                _register_login_failure(user)
            flash("아이디 또는 비밀번호가 올바르지 않습니다.")
            return render_template("login.html", username=username)

        if user["is_dormant"]:
            flash("신고 누적으로 휴면 처리된 계정입니다.")
            return render_template("login.html", username=username)

        # 로그인 성공: 실패 카운터 초기화 + 세션 고정 공격 방지를 위해 세션 재설정
        execute("UPDATE users SET failed_login = 0, lock_until = NULL WHERE id = ?", (user["id"],))
        session.clear()
        session["user_id"] = user["id"]
        session.permanent = True
        flash("로그인되었습니다.")
        return redirect(url_for("products.index"))

    return render_template("login.html")


def _register_login_failure(user):
    """로그인 실패 카운트를 올리고, 임계치를 넘으면 계정을 일정 시간 잠근다."""
    from flask import current_app
    fails = user["failed_login"] + 1
    if fails >= current_app.config["LOGIN_MAX_FAIL"]:
        execute(
            "UPDATE users SET failed_login = ?, lock_until = ? WHERE id = ?",
            (fails, next_lock_time(), user["id"]),
        )
    else:
        execute("UPDATE users SET failed_login = ? WHERE id = ?", (fails, user["id"]))


@bp.route("/logout")
def logout():
    session.clear()
    flash("로그아웃되었습니다.")
    return redirect(url_for("auth.login"))


@bp.route("/mypage", methods=["GET", "POST"])
@login_required
def mypage():
    """소개글 수정 / 비밀번호 변경."""
    user = current_user()

    if request.method == "POST":
        action = request.form.get("action")

        if action == "bio":
            bio = clean_text(request.form.get("bio", ""), 300)
            execute("UPDATE users SET bio = ? WHERE id = ?", (bio, user["id"]))
            flash("소개글이 수정되었습니다.")

        elif action == "password":
            current_pw = request.form.get("current_password", "")
            new_pw = request.form.get("new_password", "")
            # 비밀번호 변경 시 현재 비밀번호를 반드시 재확인(세션 탈취 상황에서의 피해 완화)
            if not verify_password(current_pw, user["password_hash"]):
                flash("현재 비밀번호가 올바르지 않습니다.")
                return redirect(url_for("auth.mypage"))
            err = validate_password(new_pw)
            if err:
                flash(err)
                return redirect(url_for("auth.mypage"))
            execute("UPDATE users SET password_hash = ? WHERE id = ?",
                    (hash_password(new_pw), user["id"]))
            flash("비밀번호가 변경되었습니다.")

        return redirect(url_for("auth.mypage"))

    # 내 송금 내역도 함께 보여준다.
    transfers = query(
        """SELECT t.*, s.username AS sender_name, r.username AS receiver_name
             FROM transfers t
             JOIN users s ON s.id = t.sender_id
             JOIN users r ON r.id = t.receiver_id
            WHERE t.sender_id = ? OR t.receiver_id = ?
            ORDER BY t.created_at DESC LIMIT 20""",
        (user["id"], user["id"]),
    )
    return render_template("mypage.html", user=user, transfers=transfers)


@bp.route("/user/<user_id>")
@login_required
def profile(user_id):
    """다른 사용자의 공개 프로필 + 판매 상품 조회."""
    target = query("SELECT * FROM users WHERE id = ?", (user_id,), one=True)
    if target is None:
        abort(404)
    products = query(
        "SELECT * FROM products WHERE seller_id = ? AND is_blocked = 0 ORDER BY created_at DESC",
        (user_id,),
    )
    return render_template("profile.html", target=target, products=products)
