"""
사용자 소통/신고 기능:
  * 전체 채팅 페이지
  * 1:1 채팅(방 목록 / 대화)
  * 상품·사용자 신고

실시간 메시지 송수신 자체는 events.py(SocketIO)에서 처리하고,
여기서는 페이지 렌더링과 신고 처리(HTTP)를 담당한다.
"""
from flask import (
    Blueprint, render_template, request, redirect, url_for, flash, abort
)

from db import query, execute
from extensions import limiter
from security import (
    clean_text, current_user, login_required, new_id, safe_image_save
)

bp = Blueprint("community", __name__)


def direct_room(uid1: str, uid2: str) -> str:
    """두 사용자 id 로 항상 동일한 1:1 방 이름을 만든다(순서 무관)."""
    a, b = sorted([uid1, uid2])
    return f"dm:{a}:{b}"


@bp.route("/chat")
@login_required
def chat():
    """전체 실시간 채팅 페이지. 최근 메시지 50개를 함께 내려준다."""
    recent = query(
        """SELECT m.content, m.image_path, m.created_at, m.sender_id, u.username
             FROM messages m JOIN users u ON u.id = m.sender_id
            WHERE m.room = 'global'
            ORDER BY m.created_at DESC LIMIT 50""",
    )
    recent = list(reversed(recent))   # 오래된 것부터 표시
    return render_template("chat.html", recent=recent, me=current_user())


@bp.route("/dm")
@login_required
def dm_list():
    """
    쪽지함: 내가 대화한 상대별로, 마지막 메시지와 시각을 함께 보여준다.
    상대는 방 이름(dm:a:b)에서 내 id 가 아닌 쪽으로 정확히 구한다.
    (sender 기준으로 뽑으면 '내가 보내기만 한 상대'가 빠지므로 방 기준으로 구함)
    """
    me = current_user()
    rooms = query(
        "SELECT DISTINCT room FROM messages WHERE room LIKE ? OR room LIKE ?",
        (f"dm:{me['id']}:%", f"dm:%:{me['id']}"),
    )
    convos = []
    for r in rooms:
        parts = r["room"].split(":")          # ['dm', idA, idB]
        other_id = parts[2] if parts[1] == me["id"] else parts[1]
        other = query("SELECT id, username FROM users WHERE id = ?", (other_id,), one=True)
        if other is None:
            continue
        last = query(
            "SELECT content, image_path, created_at FROM messages WHERE room = ? "
            "ORDER BY created_at DESC LIMIT 1",
            (r["room"],), one=True,
        )
        convos.append({"other": other, "last": last})
    # 최근 대화가 위로 오도록 정렬
    convos.sort(key=lambda c: c["last"]["created_at"] if c["last"] else "", reverse=True)
    return render_template("dm_list.html", convos=convos, me=me)


@bp.route("/dm/<other_id>")
@login_required
def dm(other_id):
    """특정 상대와의 1:1 채팅방."""
    me = current_user()
    other = query("SELECT * FROM users WHERE id = ?", (other_id,), one=True)
    if other is None or other["id"] == me["id"]:
        abort(404)

    room = direct_room(me["id"], other["id"])
    recent = query(
        """SELECT m.content, m.image_path, m.created_at, m.sender_id, u.username
             FROM messages m JOIN users u ON u.id = m.sender_id
            WHERE m.room = ?
            ORDER BY m.created_at DESC LIMIT 50""",
        (room,),
    )
    recent = list(reversed(recent))
    return render_template("dm.html", other=other, room=room, recent=recent, me=me)


@bp.route("/chat/upload", methods=["POST"])
@login_required
@limiter.limit("40 per hour")
def chat_upload():
    """
    채팅 사진 업로드 전용 엔드포인트.
    - 로그인 사용자만, CSRF 토큰 검증(Flask-WTF 전역)
    - safe_image_save 로 '실제 이미지인지'까지 검증하고 UUID 파일명으로 저장
    - 저장된 파일명만 돌려주고, 실제 전송은 소켓(send_message)에서 처리
    """
    name = safe_image_save(request.files.get("image"))
    if name is None:
        return {"ok": False, "error": "이미지(png/jpg/jpeg/gif/webp)만 보낼 수 있어요."}, 400
    return {"ok": True, "path": name}


@bp.route("/report", methods=["GET", "POST"])
@login_required
@limiter.limit("30 per hour")   # 신고 스팸 완화
def report():
    """
    상품 또는 사용자 신고.
    - 신고 대상 존재 여부 확인
    - 자기 자신 신고 금지
    - 동일 대상 중복 신고 금지(DB UNIQUE + 사전 체크)
    - 임계치 초과 시 자동 상품 숨김 / 유저 휴면 전환
    """
    me = current_user()
    target_type = request.values.get("type", "")
    target_id = request.values.get("target_id", "")

    if request.method == "POST":
        from flask import current_app
        reason = clean_text(request.form.get("reason", ""), 500)

        if target_type not in ("user", "product"):
            flash("잘못된 신고 대상입니다.")
            return redirect(url_for("products.index"))
        if not reason:
            flash("신고 사유를 입력해 주세요.")
            return render_template("report.html", type=target_type, target_id=target_id)

        # 대상 존재 확인 + 자기 자신 신고 방지
        if target_type == "user":
            target = query("SELECT * FROM users WHERE id = ?", (target_id,), one=True)
            if target and target["id"] == me["id"]:
                flash("자기 자신은 신고할 수 없습니다.")
                return redirect(url_for("products.index"))
        else:
            target = query("SELECT * FROM products WHERE id = ?", (target_id,), one=True)
            if target and target["seller_id"] == me["id"]:
                flash("본인이 등록한 상품은 신고할 수 없습니다.")
                return redirect(url_for("products.detail", product_id=target_id))
        if target is None:
            flash("신고 대상을 찾을 수 없습니다.")
            return redirect(url_for("products.index"))

        # 중복 신고 방지
        dup = query(
            "SELECT 1 FROM reports WHERE reporter_id = ? AND target_type = ? AND target_id = ?",
            (me["id"], target_type, target_id), one=True,
        )
        if dup:
            flash("이미 신고한 대상입니다.")
            return redirect(url_for("products.index"))

        execute(
            "INSERT INTO reports (id, reporter_id, target_type, target_id, reason) VALUES (?, ?, ?, ?, ?)",
            (new_id(), me["id"], target_type, target_id, reason),
        )

        # 누적 신고 수 갱신 + 임계치 처리
        if target_type == "product":
            execute("UPDATE products SET report_count = report_count + 1 WHERE id = ?", (target_id,))
            cnt = query("SELECT report_count FROM products WHERE id = ?", (target_id,), one=True)["report_count"]
            if cnt >= current_app.config["REPORT_BLOCK_THRESHOLD"]:
                execute("UPDATE products SET is_blocked = 1 WHERE id = ?", (target_id,))
        else:
            execute("UPDATE users SET report_count = report_count + 1 WHERE id = ?", (target_id,))
            cnt = query("SELECT report_count FROM users WHERE id = ?", (target_id,), one=True)["report_count"]
            if cnt >= current_app.config["REPORT_DORMANT_THRESHOLD"]:
                execute("UPDATE users SET is_dormant = 1 WHERE id = ?", (target_id,))

        flash("신고가 접수되었습니다.")
        return redirect(url_for("products.index"))

    # GET: 신고 폼
    if target_type not in ("user", "product") or not target_id:
        flash("신고 대상이 지정되지 않았습니다.")
        return redirect(url_for("products.index"))
    return render_template("report.html", type=target_type, target_id=target_id)
