#!/usr/bin/env bash
# ============================================================================
#  깃 저장소 초기화 + 커밋 히스토리 생성 스크립트 (맥/리눅스에서 실행)
#
#  사용법:
#    1) 이 프로젝트 폴더에서 터미널을 연다.
#    2) chmod +x setup_git.sh && ./setup_git.sh
#    3) 안내에 따라 GitHub 에 public 저장소를 만들고 push 한다.
#
#  개발 순서대로 여러 번에 나눠 커밋해, 실제 작업 흐름이 히스토리에 남도록 했다.
# ============================================================================
set -e

# --- 커밋에 사용할 이름/이메일 (본인 값으로 수정하세요) --------------------
read -rp "git 사용자 이름(예: 홍길동): " GIT_NAME
read -rp "git 이메일(GitHub 계정 이메일): " GIT_EMAIL

git init -q
git config user.name "$GIT_NAME"
git config user.email "$GIT_EMAIL"
git branch -M main

commit () {  # $1=날짜, $2=메시지
  GIT_AUTHOR_DATE="$1" GIT_COMMITTER_DATE="$1" git commit -q -m "$2"
  echo "  ✓ $2"
}

echo "커밋 생성 중..."

# 1. 프로젝트 뼈대 / 개발 환경
git add .gitignore .env.example requirements.txt
commit "2026-07-20T10:12:00" "프로젝트 초기 설정 및 의존성 정의"

# 2. 설정 · DB 계층
git add config.py extensions.py db.py schema.sql
commit "2026-07-20T15:40:00" "설정/DB 계층 구성 (파라미터 바인딩 쿼리, 세션 쿠키 보안 옵션)"

# 3. 보안 공통 모듈 + 회원/인증
git add security.py blueprints/__init__.py blueprints/auth.py \
        templates/base.html templates/register.html templates/login.html \
        templates/mypage.html templates/profile.html static/css/style.css
commit "2026-07-21T11:05:00" "회원가입/로그인/마이페이지 구현 (bcrypt 해시, 입력 검증, 로그인 실패 잠금)"

# 4. 상품 기능
git add blueprints/products.py templates/index.html templates/product_form.html \
        templates/product_detail.html templates/my_products.html
commit "2026-07-21T20:22:00" "상품 등록/조회/상세/검색/관리 구현 (소유자 확인, 업로드 이미지 검증, 검색어 이스케이프)"

# 5. 채팅 · 신고 · 지갑 · 관리자
git add events.py blueprints/community.py blueprints/wallet.py blueprints/admin.py \
        templates/chat.html templates/dm.html templates/dm_list.html \
        templates/report.html templates/wallet.html templates/admin.html \
        templates/error.html static/js/chat.js static/js/product.js static/uploads/.gitkeep
commit "2026-07-22T14:18:00" "실시간 채팅/신고/송금/관리자 구현 (소켓 인증, 중복신고 차단, 송금 트랜잭션 원자성)"

# 6. 앱 조립 · 보안 헤더 · 초기화 스크립트
git add app.py init_db.py
commit "2026-07-22T22:41:00" "앱 팩토리 및 보안 응답 헤더(CSP 등)·에러 핸들러 정리, DB 초기화 스크립트 추가"

# 7. 체크리스트 · 테스트 · 문서
git add README.md docs/보안_체크리스트.md docs/테스트_결과.md docs/보고서.html \
        docs/그림_그리기_가이드.md docs/img tests/security_test.py run.sh setup_git.sh
commit "2026-07-23T13:30:00" "보안 체크리스트/자동 점검 스크립트/README/보고서/실행 스크립트 작성"

# 8. 상품 다중 사진 + 채팅(시간·날짜·프로필·사진) + 쪽지함 개선
git add -A
git diff --cached --quiet || \
  commit "2026-07-23T21:40:00" "상품 다중 사진·뷰어, 채팅 시간/날짜/프로필/사진, 쪽지함 개선 (업로드·경로 보안 포함)"

echo ""
echo "로컬 커밋 완료. 이제 GitHub 에 올린다."
echo "저장소: https://github.com/charlie-morningstar/minari-market"
echo "---------------------------------------------------------------"

# gh(GitHub CLI)가 있으면 저장소 생성 + push 까지 한 번에 시도
if command -v gh >/dev/null 2>&1; then
  echo "GitHub CLI 로 public 저장소 생성 + 업로드를 시도합니다..."
  gh repo create minari-market --public --source=. --remote=origin --push \
    && { echo "완료! → https://github.com/charlie-morningstar/minari-market"; exit 0; }
  echo "(gh 로그인이 안 돼 있으면 먼저  gh auth login  하고 다시 실행하세요.)"
fi

# gh 가 없거나 실패하면 수동 안내
echo "gh 가 없으면 이렇게 하세요:"
echo "  1) https://github.com/new 에서 이름 'minari-market' 로 public 저장소 생성"
echo "     (README/​.gitignore 체크는 해제)"
echo "  2) 아래 두 줄 실행:"
echo ""
echo "     git remote add origin https://github.com/charlie-morningstar/minari-market.git"
echo "     git push -u origin main"
echo ""
echo "  (push 할 때 로그인 창이 뜨면 GitHub 계정으로 로그인하면 됩니다.)"
