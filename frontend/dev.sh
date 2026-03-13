#!/bin/bash
# JINXUS 프론트엔드 개발 서버 (pm2 daemon + HMR)
#
# 사용법:
#   bash dev.sh          — 서버 시작/재시작 (HMR 유지, 빠름)
#   bash dev.sh --clean  — .next 삭제 후 클린 재시작 (패키지 추가/이상 시)
#   bash dev.sh --stop   — 서버 중지
#   bash dev.sh --log    — 실시간 로그

PORT=${1:-5000}
DIR="$(cd "$(dirname "$0")" && pwd)"
PM2="$HOME/.local/bin/pm2"

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

# --clean 플래그: .next 삭제
if [ "$1" = "--clean" ]; then
  echo "[JINXUS] 클린 빌드 (캐시 삭제 중...)"
  rm -rf "$DIR/.next"
  PORT=5000
fi

# 기존 pm2 프로세스 종료
$PM2 delete jinxus-frontend 2>/dev/null

echo "[JINXUS] 프론트엔드 시작 → http://100.75.83.105:$PORT (HMR 활성)"
$PM2 start "npx next dev -p $PORT -H 0.0.0.0" \
  --name jinxus-frontend \
  --no-autorestart \
  --log "$DIR/logs/frontend.log" \
  --error "$DIR/logs/frontend.err"

echo "[JINXUS] 파일 수정 시 브라우저가 자동으로 업데이트됩니다"
