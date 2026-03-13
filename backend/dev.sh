#!/bin/bash
# JINXUS 백엔드 로컬 개발 서버 (Docker 없이)
# Redis/Qdrant는 Docker 컨테이너 그대로 사용, 백엔드만 호스트에서 실행

set -e

cd "$(dirname "$0")"

# Docker 백엔드 컨테이너 중지 (포트 충돌 방지)
echo ">>> Docker 백엔드 컨테이너 중지..."
docker compose stop jinxus 2>/dev/null || true

# 호스트 → Docker 포트 매핑 (Redis 16379, Qdrant 16333)
export REDIS_HOST=localhost
export REDIS_PORT=16379
export QDRANT_HOST=localhost
export QDRANT_PORT=16333
export JINXUS_PORT=19000
export JINXUS_DEBUG=true

# .env 나머지 변수 로드 (API 키 등)
set -a
source .env
set +a

# 위에서 설정한 포트 다시 덮어쓰기 (.env가 6379/6333이라서)
export REDIS_PORT=16379
export QDRANT_PORT=16333

echo ">>> Redis: $REDIS_HOST:$REDIS_PORT"
echo ">>> Qdrant: $QDRANT_HOST:$QDRANT_PORT"
echo ">>> JINXUS: http://0.0.0.0:$JINXUS_PORT"
echo ""

# uvicorn 실행 (--reload로 코드 변경 시 자동 재시작)
exec uvicorn jinxus.api.server:create_app --factory \
    --host 0.0.0.0 \
    --port "$JINXUS_PORT" \
    --reload \
    --reload-dir jinxus
