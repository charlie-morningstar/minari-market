"""
확장 객체 초기화.

여러 모듈에서 순환 참조 없이 같은 확장 인스턴스를 공유하기 위해
별도 파일로 분리했다. (app.py 에서 init_app 으로 앱에 연결한다)
"""
from flask_socketio import SocketIO
from flask_wtf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# 실시간 채팅용. async_mode="threading" 은 별도 비동기 라이브러리(eventlet 등)
# 없이 표준 스레드로 동작해 macOS/Windows 어디서든 설치가 단순하다.
socketio = SocketIO(cors_allowed_origins="*", async_mode="threading")

# 모든 POST 요청에 대해 CSRF 토큰을 강제 검증한다.
csrf = CSRFProtect()

# IP 단위 요청 속도 제한. 로그인 무차별 대입, 채팅/신고 스팸을 완화한다.
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["300 per hour"],
    storage_uri="memory://",
)
