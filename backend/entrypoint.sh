#!/bin/bash
# JINXUS 백엔드 엔트리포인트
# requirements.txt 변경 시 자동 pip install (빌드 없이 패키지 추가 가능)

set -e

# requirements.txt 해시 비교 → 변경되었으면 pip install
REQ_HASH_FILE="/tmp/.requirements_hash"
CURRENT_HASH=$(md5sum /app/requirements.txt | cut -d' ' -f1)

if [ -f "$REQ_HASH_FILE" ]; then
    SAVED_HASH=$(cat "$REQ_HASH_FILE")
else
    SAVED_HASH=""
fi

if [ "$CURRENT_HASH" != "$SAVED_HASH" ]; then
    echo "[entrypoint] requirements.txt 변경 감지 → pip install 실행..."
    pip install --no-cache-dir -r /app/requirements.txt -q 2>&1 | tail -3
    echo "$CURRENT_HASH" > "$REQ_HASH_FILE"
    echo "[entrypoint] pip install 완료"
else
    echo "[entrypoint] requirements.txt 변경 없음 → 건너뜀"
fi

# 서버 실행
exec python main.py
