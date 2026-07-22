# 서버 실행 진입점.  ->  python app.py  (기본 5001 포트)
# create_app() 에서 설정, 확장(소켓/CSRF/제한), 블루프린트, 보안 헤더,
# 에러 페이지를 다 붙여서 앱을 만든다.
import os

from flask import Flask, render_template, g

from config import Config
from extensions import socketio, csrf, limiter
from db import close_db, init_db, query
from security import current_user


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # 업로드/DB 디렉터리 준비
    os.makedirs(app.config["UPLOAD_DIR"], exist_ok=True)
    os.makedirs(os.path.dirname(app.config["DATABASE"]), exist_ok=True)

    # 확장 연결
    csrf.init_app(app)
    limiter.init_app(app)
    socketio.init_app(app)

    # 요청 종료 시 DB 커넥션 정리
    app.teardown_appcontext(close_db)

    # 블루프린트 등록
    from blueprints.auth import bp as auth_bp
    from blueprints.products import bp as products_bp
    from blueprints.community import bp as community_bp
    from blueprints.wallet import bp as wallet_bp
    from blueprints.admin import bp as admin_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(products_bp)
    app.register_blueprint(community_bp)
    app.register_blueprint(wallet_bp)
    app.register_blueprint(admin_bp)

    # 모든 템플릿에서 현재 로그인 사용자를 참조할 수 있게 주입
    @app.context_processor
    def inject_user():
        return {"me": current_user()}

    # --- 보안 응답 헤더 ------------------------------------------------------
    @app.after_request
    def set_security_headers(resp):
        # 클릭재킹 방지
        resp.headers["X-Frame-Options"] = "DENY"
        # MIME 스니핑 방지
        resp.headers["X-Content-Type-Options"] = "nosniff"
        # 리퍼러 최소화
        resp.headers["Referrer-Policy"] = "same-origin"
        # CSP: 스크립트/스타일은 자기 출처와 필요한 CDN 만 허용해 XSS 영향 축소
        resp.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "img-src 'self' data:; "
            "script-src 'self' https://cdn.socket.io; "
            "style-src 'self' 'unsafe-inline'; "
            "connect-src 'self' ws: wss:"
        )
        return resp

    # --- 에러 핸들러(내부 정보 노출 없이 사용자 친화적 안내) -----------------
    @app.errorhandler(403)
    def forbidden(e):
        return render_template("error.html", code=403, message="접근 권한이 없습니다."), 403

    @app.errorhandler(404)
    def not_found(e):
        return render_template("error.html", code=404, message="페이지를 찾을 수 없습니다."), 404

    @app.errorhandler(413)
    def too_large(e):
        return render_template("error.html", code=413, message="업로드 용량이 너무 큽니다."), 413

    @app.errorhandler(429)
    def too_many(e):
        return render_template("error.html", code=429, message="요청이 너무 많습니다. 잠시 후 다시 시도해 주세요."), 429

    @app.errorhandler(500)
    def server_error(e):
        # 상세 오류(스택 트레이스 등)는 사용자에게 노출하지 않는다.
        return render_template("error.html", code=500, message="서버 오류가 발생했습니다."), 500

    # CLI: flask --app app init-db 로 DB 초기화
    @app.cli.command("init-db")
    def init_db_command():
        init_db()
        print("데이터베이스를 초기화했습니다.")

    # SocketIO 이벤트 핸들러 등록(임포트 시 @socketio.on 이 등록됨)
    with app.app_context():
        import events  # noqa: F401

    return app


app = create_app()


if __name__ == "__main__":
    # 포트는 환경변수 PORT 로 바꿀 수 있다. 기본값을 5001 로 둔 이유:
    # macOS 는 5000 번을 AirPlay 수신 기능이 선점하고 있어 충돌이 잦다.
    port = int(os.environ.get("PORT", 5001))
    # allow_unsafe_werkzeug: 개발 서버로 SocketIO 를 구동하기 위한 옵션
    socketio.run(app, host="0.0.0.0", port=port, debug=False,
                 allow_unsafe_werkzeug=True)
