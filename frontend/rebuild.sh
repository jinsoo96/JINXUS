#!/bin/bash
# JINXUS 프론트엔드 재빌드 + 재시작 스크립트
# 사용: ./rebuild.sh [port] (기본: 1818)

PORT=${1:-1818}
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

echo "[JINXUS] 프론트엔드 재빌드 시작..."

# 기존 서버 종료
PID=$(lsof -ti:$PORT 2>/dev/null)
if [ -n "$PID" ]; then
  echo "[JINXUS] 포트 $PORT 프로세스(PID: $PID) 종료"
  kill -9 $PID 2>/dev/null
  sleep 1
fi

# 빌드 캐시 삭제 + 재빌드
rm -rf .next
echo "[JINXUS] 빌드 중..."
npx next build 2>&1

if [ $? -ne 0 ]; then
  echo "[JINXUS] 빌드 실패!"
  exit 1
fi

# 서버 시작
echo "[JINXUS] 포트 $PORT에서 서버 시작..."
nohup npx next start -p $PORT > /tmp/jinxus-frontend.log 2>&1 &
sleep 2

# 확인
if ss -tlnp | grep -q ":$PORT"; then
  echo "[JINXUS] 프론트엔드 재빌드 완료! http://localhost:$PORT"
else
  echo "[JINXUS] 서버 시작 실패. 로그: /tmp/jinxus-frontend.log"
  exit 1
fi
