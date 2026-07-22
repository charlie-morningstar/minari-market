"""
가상 잔액(포인트) 지갑 & 송금.

설계 메모(멘토 질문: "실제로 돈을 다루는 정도까지?"):
  실제 결제(PG/은행 연동)는 이 과제 범위를 벗어나고, 실제 금전을 다루면
  전자금융거래법 등 규제 대상이 된다. 그래서 '가상 잔액(포인트)'을 계정마다
  두고 사용자끼리 이체하는 형태로 구현했다. 대신 실제 금융 로직에서
  반드시 지켜야 할 안전장치(잔액 검증, 음수/자기 자신 이체 차단, 트랜잭션
  원자성)는 그대로 반영해 '보안을 신경 쓴 흔적'이 남도록 했다.
"""
from flask import (
    Blueprint, render_template, request, redirect, url_for, flash
)

from db import query, get_db
from extensions import limiter
from security import clean_text, current_user, login_required, new_id

bp = Blueprint("wallet", __name__)


@bp.route("/wallet")
@login_required
def wallet():
    me = current_user()
    history = query(
        """SELECT t.*, s.username AS sender_name, r.username AS receiver_name
             FROM transfers t
             JOIN users s ON s.id = t.sender_id
             JOIN users r ON r.id = t.receiver_id
            WHERE t.sender_id = ? OR t.receiver_id = ?
            ORDER BY t.created_at DESC LIMIT 30""",
        (me["id"], me["id"]),
    )
    return render_template("wallet.html", me=me, history=history)


@bp.route("/wallet/charge", methods=["POST"])
@login_required
@limiter.limit("20 per hour")
def charge():
    """
    데모용 잔액 충전(실서비스라면 결제 연동 자리).
    1회 충전 한도를 두어 비정상 입력을 막는다.
    """
    me = current_user()
    try:
        amount = int(request.form.get("amount", "").strip())
    except ValueError:
        flash("충전 금액은 숫자로 입력해 주세요.")
        return redirect(url_for("wallet.wallet"))
    if not (0 < amount <= 1_000_000):
        flash("1회 충전 금액은 1 ~ 1,000,000 포인트여야 합니다.")
        return redirect(url_for("wallet.wallet"))

    db = get_db()
    db.execute("UPDATE users SET balance = balance + ? WHERE id = ?", (amount, me["id"]))
    db.commit()
    flash(f"{amount:,} 포인트가 충전되었습니다.")
    return redirect(url_for("wallet.wallet"))


@bp.route("/wallet/transfer", methods=["POST"])
@login_required
@limiter.limit("60 per hour")
def transfer():
    """
    다른 사용자에게 포인트 송금.
    - 금액은 양의 정수만
    - 자기 자신에게 송금 금지
    - 잔액 부족 시 거부
    - 조회~차감~증액~기록을 하나의 트랜잭션으로 처리(원자성).
      중간에 실패하면 전체 롤백하여 '돈이 사라지거나 복제되는' 상황을 막는다.
    """
    me = current_user()
    to_username = clean_text(request.form.get("to_username", ""), 20)
    memo = clean_text(request.form.get("memo", ""), 100)
    try:
        amount = int(request.form.get("amount", "").strip())
    except ValueError:
        flash("송금 금액은 숫자로 입력해 주세요.")
        return redirect(url_for("wallet.wallet"))

    if amount <= 0:
        flash("송금 금액은 1 포인트 이상이어야 합니다.")
        return redirect(url_for("wallet.wallet"))

    receiver = query("SELECT * FROM users WHERE username = ?", (to_username,), one=True)
    if receiver is None:
        flash("받는 사람을 찾을 수 없습니다.")
        return redirect(url_for("wallet.wallet"))
    if receiver["id"] == me["id"]:
        flash("자기 자신에게는 송금할 수 없습니다.")
        return redirect(url_for("wallet.wallet"))

    db = get_db()
    try:
        # BEGIN IMMEDIATE 로 즉시 쓰기 잠금을 잡아 동시 이체 경합을 막는다.
        db.execute("BEGIN IMMEDIATE")
        sender = db.execute("SELECT balance FROM users WHERE id = ?", (me["id"],)).fetchone()
        if sender["balance"] < amount:
            db.execute("ROLLBACK")
            flash("잔액이 부족합니다.")
            return redirect(url_for("wallet.wallet"))

        db.execute("UPDATE users SET balance = balance - ? WHERE id = ?", (amount, me["id"]))
        db.execute("UPDATE users SET balance = balance + ? WHERE id = ?", (amount, receiver["id"]))
        db.execute(
            "INSERT INTO transfers (id, sender_id, receiver_id, amount, memo) VALUES (?, ?, ?, ?, ?)",
            (new_id(), me["id"], receiver["id"], amount, memo),
        )
        db.execute("COMMIT")
    except Exception:
        db.execute("ROLLBACK")
        flash("송금 처리 중 오류가 발생했습니다. 다시 시도해 주세요.")
        return redirect(url_for("wallet.wallet"))

    flash(f"{receiver['username']}님에게 {amount:,} 포인트를 송금했습니다.")
    return redirect(url_for("wallet.wallet"))
