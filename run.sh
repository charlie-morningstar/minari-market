#!/usr/bin/env bash
# 한 번에 실행: 가상환경 만들고 → 패키지 깔고 → .env 준비 → DB 만들고 → 서버 켠다.
#   chmod +x run.sh && ./run.sh
# 이미 세팅돼 있으면 알아서 건너뛴다.
set -e
cd "$(dirname "$0")"

# 1) 가상환경
if [ ! -d ".venv" ]; then
  echo "[1/4] 가상환경 만드는 중..."
  python3 -m venv .venv
fi
source .venv/bin/activate

# 2) 패키지
echo "[2/4] 패키지 확인/설치..."
pip install -q -r requirements.txt

# 3) .env (없으면 예시 복사하고 SECRET_KEY 자동 생성)
if [ ! -f ".env" ]; then
  echo "[3/4] .env 생성 + SECRET_KEY 자동 발급..."
  cp .env.example .env
  KEY=$(python -c "import secrets; print(secrets.token_hex(32))")
  # macOS/리눅스 sed 호환을 위해 임시파일 방식 사용
  python - "$KEY" <<'PY'
import sys, re, pathlib
key = sys.argv[1]
p = pathlib.Path(".env")
p.write_text(re.sub(r"^SECRET_KEY=.*$", f"SECRET_KEY={key}", p.read_text(), flags=re.M))
PY
fi

# 4) DB (없을 때만 초기화)
if [ ! -f "instance/market.db" ]; then
  echo "[4/4] 데이터베이스 초기화..."
  python init_db.py
fi

echo ""
echo "서버를 켭니다 →  http://localhost:5001   (끄려면 Ctrl+C)"
python app.py
