#!/bin/bash
# JINXUS 프론트엔드 서버 관리
#
# 사용법:
#   bash dev.sh           — 프로덕션 빌드 후 시작 (기본값)
#   bash dev.sh --dev     — 개발 서버 (HMR, Tailscale IP로만 접근)
#   bash dev.sh --rebuild — .next 삭제 후 프로덕션 클린 빌드 + 시작
#   bash dev.sh --stop    — 서버 중지
#   bash dev.sh --log     — 실시간 로그

DIR="$(cd "$(dirname "$0")" && pwd)"
PM2="$HOME/.local/bin/pm2"
PORT=5000

# 특수 명령 처리
if [ "$1" = "--stop" ]; then
  $PM2 delete jinxus-frontend 2>/dev/null && echo "[JINXUS] 프론트엔드 중지됨"
  exit 0
fi
if [ "$1" = "--log" ]; then
  $PM2 logs jinxus-frontend
  exit 0
fi

cd "$DIR"
mkdir -p "$DIR/logs"

# package.json 해시 비교 → 변경 시 자동 npm install
HASH_FILE="$DIR/.package_hash"
CURRENT_HASH=$(md5sum "$DIR/package.json" 2>/dev/null | cut -d' ' -f1)
SAVED_HASH=""
[ -f "$HASH_FILE" ] && SAVED_HASH=$(cat "$HASH_FILE")

if [ "$CURRENT_HASH" != "$SAVED_HASH" ] || [ ! -d "$DIR/node_modules" ]; then
  echo "[JINXUS] package.json 변경 감지 → npm install 실행..."
  npm install --prefer-offline 2>&1 | tail -3
  echo "$CURRENT_HASH" > "$HASH_FILE"
fi

$PM2 delete jinxus-frontend 2>/dev/null

# --dev 모드: HMR 개발 서버
if [ "$1" = "--dev" ]; then
  echo "[JINXUS] 개발 서버 시작 (HMR) → http://100.75.83.105:$PORT"
  $PM2 start "npx next dev -p $PORT -H 0.0.0.0" \
    --name jinxus-frontend \
    --no-autorestart \
    --log "$DIR/logs/frontend.log" \
    --error "$DIR/logs/frontend.err"
  echo "[JINXUS] 파일 수정 시 브라우저 자동 업데이트 (HMR 활성)"
  exit 0
fi

# 프로덕션 모드 (기본값)
# 소스 해시 비교 → 변경 시 자동 빌드
SRC_HASH_FILE="$DIR/.src_hash"
CURRENT_SRC_HASH=$(find "$DIR/src" "$DIR/public" "$DIR/next.config.js" "$DIR/tailwind.config.ts" "$DIR/tsconfig.json" \
  -type f 2>/dev/null | sort | xargs md5sum 2>/dev/null | md5sum | cut -d' ' -f1)
SAVED_SRC_HASH=""
[ -f "$SRC_HASH_FILE" ] && SAVED_SRC_HASH=$(cat "$SRC_HASH_FILE")

NEEDS_BUILD=false
if [ "$1" = "--rebuild" ]; then
  NEEDS_BUILD=true
  rm -rf "$DIR/.next"
elif [ ! -d "$DIR/.next" ]; then
  NEEDS_BUILD=true
elif [ "$CURRENT_SRC_HASH" != "$SAVED_SRC_HASH" ]; then
  echo "[JINXUS] 소스 변경 감지 → 자동 빌드"
  NEEDS_BUILD=true
fi

if [ "$NEEDS_BUILD" = true ]; then
  echo "[JINXUS] 프로덕션 빌드 중..."
  npx next build 2>&1 | tail -15
  if [ $? -eq 0 ]; then
    echo "$CURRENT_SRC_HASH" > "$SRC_HASH_FILE"
    echo "[JINXUS] 빌드 완료"
  else
    echo "[JINXUS] 빌드 실패 — 이전 빌드로 서빙"
  fi
else
  echo "[JINXUS] 소스 변경 없음 → 기존 빌드 사용"
fi

echo "[JINXUS] 프로덕션 서버 시작 → http://100.75.83.105:$PORT"
$PM2 start "npx next start -p $PORT -H 0.0.0.0" \
  --name jinxus-frontend \
  --no-autorestart \
  --log "$DIR/logs/frontend.log" \
  --error "$DIR/logs/frontend.err"

echo "[JINXUS] 코드 수정 후 반영: bash dev.sh --rebuild"
