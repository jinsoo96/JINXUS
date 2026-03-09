#!/bin/bash
# JINXUS 프론트엔드 개발 모드 (핫리로드)
# 사용: ./dev.sh [port] (기본: 5000)
# 코드 수정 시 자동 반영됨

PORT=${1:-5000}
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

# 기존 프로세스 종료
PID=$(lsof -ti:$PORT 2>/dev/null)
if [ -n "$PID" ]; then
  echo "[JINXUS] 포트 $PORT 프로세스(PID: $PID) 종료"
  kill -9 $PID 2>/dev/null
  sleep 1
fi

echo "[JINXUS] 개발 모드 시작 (핫리로드) — http://localhost:$PORT"
echo "[JINXUS] 원격 접속: http://100.75.83.105:$PORT (Tailscale)"
exec npx next dev -p $PORT -H 0.0.0.0
