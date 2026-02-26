#!/bin/bash

# JINXUS 서버 시작 스크립트 (tmux로 24시간 운영)
# 사용법: ./start.sh

set -e

echo "
╔═══════════════════════════════════════════════════════════╗
║                   JINXUS Server Start                      ║
╚═══════════════════════════════════════════════════════════╝
"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# 현재 디렉토리 확인
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Docker 컨테이너 확인 및 시작
echo "🐳 Docker 컨테이너 확인 중..."

# Redis
if ! docker ps --format '{{.Names}}' | grep -q 'jinxus-redis'; then
    if docker ps -a --format '{{.Names}}' | grep -q 'jinxus-redis'; then
        docker start jinxus-redis > /dev/null
    else
        docker run -d --name jinxus-redis -p 6379:6379 redis:7-alpine > /dev/null
    fi
fi
echo -e "${GREEN}✓ Redis 실행 중${NC}"

# Qdrant
if ! docker ps --format '{{.Names}}' | grep -q 'jinxus-qdrant'; then
    if docker ps -a --format '{{.Names}}' | grep -q 'jinxus-qdrant'; then
        docker start jinxus-qdrant > /dev/null
    else
        docker run -d --name jinxus-qdrant -p 6333:6333 qdrant/qdrant > /dev/null
    fi
fi
echo -e "${GREEN}✓ Qdrant 실행 중${NC}"

# 기존 tmux 세션 확인
if tmux has-session -t jinxus 2>/dev/null; then
    echo -e "${YELLOW}⚠ 기존 jinxus 세션이 있습니다${NC}"
    echo ""
    echo "선택하세요:"
    echo "  1) 기존 세션에 붙기 (tmux attach -t jinxus)"
    echo "  2) 기존 세션 종료 후 새로 시작"
    echo "  3) 취소"
    read -p "선택 (1/2/3): " choice

    case $choice in
        1)
            echo "기존 세션에 붙습니다..."
            tmux attach -t jinxus
            exit 0
            ;;
        2)
            echo "기존 세션 종료 중..."
            tmux kill-session -t jinxus 2>/dev/null || true
            ;;
        3)
            echo "취소됨"
            exit 0
            ;;
        *)
            echo "잘못된 선택"
            exit 1
            ;;
    esac
fi

# 포트 확인
if lsof -i :9000 > /dev/null 2>&1; then
    echo -e "${YELLOW}⚠ 포트 9000이 이미 사용 중입니다${NC}"
    read -p "기존 프로세스 종료? (y/n): " kill_choice
    if [[ $kill_choice == "y" ]]; then
        pkill -f "python3 main.py" 2>/dev/null || true
        sleep 2
    fi
fi

# tmux 세션 생성 및 서버 시작
echo ""
echo "🚀 JINXUS 서버 시작 중..."

# 백엔드 세션
tmux new-session -d -s jinxus -n backend "cd $SCRIPT_DIR && python3 main.py"

# 프론트엔드 - 이미 실행 중인지 확인
if lsof -i :1818 > /dev/null 2>&1; then
    echo -e "${YELLOW}⚠ 프론트엔드 이미 실행 중 (포트 1818)${NC}"
else
    # 프론트엔드 윈도우 추가
    tmux new-window -t jinxus -n frontend "cd $SCRIPT_DIR/frontend && npm run dev"
    echo -e "${GREEN}✓ 프론트엔드 시작됨${NC}"
fi

# 백엔드 윈도우로 돌아가기
tmux select-window -t jinxus:backend

sleep 3

# 서버 상태 확인
if curl -s http://localhost:9000/status > /dev/null 2>&1; then
    echo -e "${GREEN}✓ 백엔드 서버 시작됨 (포트 9000)${NC}"
else
    echo -e "${YELLOW}⚠ 백엔드 서버 시작 중... (잠시 대기)${NC}"
fi

echo ""
echo "═══════════════════════════════════════════════════════════"
echo -e "${GREEN}✓ JINXUS 서버 시작 완료!${NC}"
echo "═══════════════════════════════════════════════════════════"
echo ""
echo "📌 접속 정보:"
echo "   - 웹 UI: http://localhost:1818"
echo "   - API: http://localhost:9000"
echo "   - API 문서: http://localhost:9000/docs"
echo ""
echo "📌 tmux 명령어:"
echo "   - 세션 붙기: tmux attach -t jinxus"
echo "   - 세션 분리: Ctrl+B, D"
echo "   - 윈도우 전환: Ctrl+B, n (다음) / Ctrl+B, p (이전)"
echo "   - 세션 종료: tmux kill-session -t jinxus"
echo ""
echo "📌 서버 상태 확인:"
echo "   curl http://localhost:9000/status"
echo ""

# 세션에 붙을지 선택
read -p "tmux 세션에 붙으시겠습니까? (y/n): " attach_choice
if [[ $attach_choice == "y" ]]; then
    tmux attach -t jinxus
fi
