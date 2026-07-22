# 실시간 채팅(SocketIO) 처리.
# 여기서 조심할 것들:
#  - 로그인 안 된 소켓이 보내는 메시지는 그냥 무시
#  - 빈 메시지 / 너무 긴 메시지 거르기
#  - XSS: 서버에서 한 번 escape + 클라이언트도 textContent 로 (이중으로 막음)
#  - 도배 방지: 같은 사람이 너무 빠르게 연속으로 못 보내게
#  - 1:1 방은 방 이름(dm:a:b)에 내 id 가 들어있을 때만 입장 허용
import os
import time
from datetime import datetime
from collections import defaultdict

from flask import session, current_app
from flask_socketio import join_room, emit

from extensions import socketio
from db import query, execute
from security import new_id, is_valid_stored_image

# 사용자별 최근 메시지 전송 시각 기록(간단한 도배 방지)
_last_sent = defaultdict(float)
_MIN_INTERVAL = 0.5          # 최소 전송 간격(초)
_MAX_MESSAGE_LEN = 500       # 메시지 최대 길이


def _authed_user():
    """소켓 세션에서 현재 로그인 사용자를 조회(없으면 None)."""
    uid = session.get("user_id")
    if not uid:
        return None
    user = query("SELECT id, username, is_dormant FROM users WHERE id = ?", (uid,), one=True)
    if user is None or user["is_dormant"]:
        return None
    return user


def _rate_ok(uid: str) -> bool:
    now = time.time()
    if now - _last_sent[uid] < _MIN_INTERVAL:
        return False
    _last_sent[uid] = now
    return True


@socketio.on("join")
def on_join(data):
    """방 입장. global 은 모두 허용, dm 방은 참여 당사자만 허용."""
    user = _authed_user()
    if user is None:
        return
    room = (data or {}).get("room", "global")

    if room != "global":
        # dm:<idA>:<idB> 형식이고, 내 id 가 포함될 때만 입장 허용
        if not room.startswith("dm:") or user["id"] not in room.split(":"):
            return
    join_room(room)


@socketio.on("send_message")
def on_send_message(data):
    """메시지 수신 → 검증 → 저장 → 같은 방에 방송. (글 또는 사진)"""
    user = _authed_user()
    if user is None:
        return

    data = data or {}
    room = data.get("room", "global")
    content = (data.get("content") or "").strip()
    image = (data.get("image") or "").strip()

    # 방 접근 통제(전송 시에도 재확인)
    if room != "global" and (not room.startswith("dm:") or user["id"] not in room.split(":")):
        return

    # 사진 메시지면 파일명 형식을 엄격 검증하고, 실제로 우리 업로드 폴더에
    # 저장된 파일인지까지 확인한다(임의 경로 주입 차단).
    if image:
        if not is_valid_stored_image(image):
            return
        if not os.path.exists(os.path.join(current_app.config["UPLOAD_DIR"], image)):
            return
    else:
        # 글 메시지: 빈 값/과도한 길이 거르기
        if not content or len(content) > _MAX_MESSAGE_LEN:
            return

    # 도배 방지
    if not _rate_ok(user["id"]):
        return

    # created_at 을 서버가 명시적으로 넣어, 기록과 실시간 표시의 시간이 어긋나지 않게 함
    now = datetime.now()
    execute(
        "INSERT INTO messages (id, room, sender_id, content, image_path, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (new_id(), room, user["id"], "" if image else content,
         image or None, now.strftime("%Y-%m-%d %H:%M:%S")),
    )

    # 원문 그대로 방송한다. 클라이언트(chat.js)는 이 값을 반드시 textContent 로만
    # 넣어(innerHTML 금지) 태그가 실행되지 않게 처리한다 → XSS 방지.
    emit(
        "new_message",
        {
            "username": user["username"],
            "sender_id": user["id"],
            "content": "" if image else content,
            "image": image or "",
            "date": now.strftime("%Y-%m-%d"),
            "time": now.strftime("%H:%M"),
        },
        room=room,
    )
