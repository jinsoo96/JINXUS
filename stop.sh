#!/bin/bash

# JINXUS 서버 중지 스크립트 (백엔드 + 프론트엔드)
# 사용법: ./stop.sh

echo "
╔═══════════════════════════════════════════════════════════╗
║                   JINXUS Server Stop                       ║
╚═══════════════════════════════════════════════════════════╝
"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# tmux 세션 종료 (백엔드 + 프론트엔드 모두)
if tmux has-session -t jinxus 2>/dev/null; then
    tmux kill-session -t jinxus
    echo -e "${GREEN}✓ JINXUS 서버 세션 종료됨 (백엔드 + 프론트엔드)${NC}"
else
    echo -e "${YELLOW}⚠ 실행 중인 jinxus 세션 없음${NC}"
fi

# 남아있는 프로세스 정리
if pkill -f "python3 main.py" 2>/dev/null; then
    echo -e "${GREEN}✓ 백엔드 프로세스 종료${NC}"
fi

if pkill -f "next dev" 2>/dev/null; then
    echo -e "${GREEN}✓ 프론트엔드 프로세스 종료${NC}"
fi

if pkill -f "npm run dev" 2>/dev/null; then
    echo -e "${GREEN}✓ npm 프로세스 종료${NC}"
fi

# 포트 확인
sleep 1
if lsof -i :19000 > /dev/null 2>&1; then
    echo -e "${YELLOW}⚠ 포트 19000 아직 사용 중 - 강제 종료 시도${NC}"
    kill -9 $(lsof -t -i :19000) 2>/dev/null || true
fi

if lsof -i :1818 > /dev/null 2>&1; then
    echo -e "${YELLOW}⚠ 포트 1818 아직 사용 중 - 강제 종료 시도${NC}"
    kill -9 $(lsof -t -i :1818) 2>/dev/null || true
fi

echo ""
read -p "Docker 컨테이너도 중지하시겠습니까? (y/n): " docker_choice
if [[ $docker_choice == "y" ]]; then
    docker stop jinxus-redis jinxus-qdrant 2>/dev/null || true
    echo -e "${GREEN}✓ Docker 컨테이너 중지됨${NC}"
fi

echo ""
echo -e "${GREEN}✓ JINXUS 서버 중지 완료${NC}"
echo ""
echo "다시 시작하려면: ./start.sh"
