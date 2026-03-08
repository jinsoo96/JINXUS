#!/bin/bash

# JINXUS Daemon 관리 스크립트
# 사용법: ./daemon.sh [start|stop|restart|status|install|uninstall|logs]

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PLIST_NAME="com.jinxus.server"
PLIST_PATH="$HOME/Library/LaunchAgents/${PLIST_NAME}.plist"
SOURCE_PLIST="$SCRIPT_DIR/daemon/jinxus.plist"
LOG_FILE="/tmp/jinxus_daemon.log"
ERROR_LOG="/tmp/jinxus_daemon_error.log"

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

print_status() {
    echo -e "${GREEN}✓${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

case "$1" in
    start)
        echo "JINXUS Daemon 시작 중..."

        # Docker 컨테이너 확인
        if ! docker ps --format '{{.Names}}' | grep -q 'jinxus-redis'; then
            print_warning "Redis 컨테이너 시작 중..."
            if docker ps -a --format '{{.Names}}' | grep -q 'jinxus-redis'; then
                docker start jinxus-redis > /dev/null
            else
                docker run -d --name jinxus-redis -p 16379:6379 redis:7-alpine > /dev/null
            fi
        fi

        if ! docker ps --format '{{.Names}}' | grep -q 'jinxus-qdrant'; then
            print_warning "Qdrant 컨테이너 시작 중..."
            if docker ps -a --format '{{.Names}}' | grep -q 'jinxus-qdrant'; then
                docker start jinxus-qdrant > /dev/null
            else
                docker run -d --name jinxus-qdrant -p 16333:6333 qdrant/qdrant > /dev/null
            fi
        fi

        # launchctl로 시작
        if [ -f "$PLIST_PATH" ]; then
            launchctl load "$PLIST_PATH" 2>/dev/null || true
            launchctl start "$PLIST_NAME" 2>/dev/null || true
            sleep 3

            if curl -s http://localhost:19000/status > /dev/null 2>&1; then
                print_status "JINXUS Daemon 시작됨 (포트 19000)"
            else
                print_warning "서버 시작 중... 잠시 후 확인"
            fi
        else
            print_error "Daemon 설치되지 않음. './daemon.sh install' 먼저 실행"
            exit 1
        fi
        ;;

    stop)
        echo "JINXUS Daemon 중지 중..."
        if [ -f "$PLIST_PATH" ]; then
            launchctl stop "$PLIST_NAME" 2>/dev/null || true
            launchctl unload "$PLIST_PATH" 2>/dev/null || true
            print_status "JINXUS Daemon 중지됨"
        else
            # 직접 프로세스 종료
            pkill -f "python.*main.py" 2>/dev/null || true
            print_status "JINXUS 프로세스 종료됨"
        fi
        ;;

    restart)
        $0 stop
        sleep 2
        $0 start
        ;;

    status)
        echo "JINXUS Daemon 상태:"
        echo ""

        # 프로세스 확인 (포트 19000 기준)
        PID=$(lsof -ti :19000 2>/dev/null | head -1)
        if [ -n "$PID" ]; then
            print_status "프로세스 실행 중 (PID: $PID)"
        else
            print_error "프로세스 실행 안됨"
        fi

        # API 확인
        if curl -s http://localhost:19000/status > /dev/null 2>&1; then
            STATUS=$(curl -s http://localhost:19000/status | python3 -c "import sys,json; d=json.load(sys.stdin); print(f\"가동시간: {d['uptime_seconds']}초, Redis: {'연결' if d['redis_connected'] else '끊김'}, Qdrant: {'연결' if d['qdrant_connected'] else '끊김'}\")")
            print_status "API 응답 정상"
            echo "    $STATUS"
        else
            print_error "API 응답 없음"
        fi

        # Docker 확인
        echo ""
        echo "Docker 컨테이너:"
        docker ps --format "  {{.Names}}: {{.Status}}" | grep jinxus || echo "  (없음)"

        # Daemon 설치 여부
        echo ""
        if [ -f "$PLIST_PATH" ]; then
            print_status "Daemon 설치됨"
        else
            print_warning "Daemon 미설치 ('./daemon.sh install'로 설치)"
        fi
        ;;

    install)
        echo "JINXUS Daemon 설치 중..."

        # LaunchAgents 디렉토리 생성
        mkdir -p "$HOME/Library/LaunchAgents"

        # plist 파일 복사 및 경로 업데이트
        sed "s|/Users/jinsookim/Desktop/JINXUS|$SCRIPT_DIR|g" "$SOURCE_PLIST" > "$PLIST_PATH"

        # 권한 설정
        chmod 644 "$PLIST_PATH"

        print_status "Daemon 설치 완료"
        echo ""
        echo "사용법:"
        echo "  ./daemon.sh start   - 시작 (부팅 시 자동 시작)"
        echo "  ./daemon.sh stop    - 중지"
        echo "  ./daemon.sh status  - 상태 확인"
        echo "  ./daemon.sh logs    - 로그 보기"
        ;;

    uninstall)
        echo "JINXUS Daemon 제거 중..."

        # 먼저 중지
        $0 stop 2>/dev/null || true

        # plist 파일 삭제
        if [ -f "$PLIST_PATH" ]; then
            rm -f "$PLIST_PATH"
            print_status "Daemon 제거 완료"
        else
            print_warning "이미 제거됨"
        fi
        ;;

    logs)
        echo "JINXUS Daemon 로그:"
        echo "===================="
        if [ -f "$LOG_FILE" ]; then
            tail -100 "$LOG_FILE"
        else
            echo "(로그 파일 없음)"
        fi

        if [ -f "$ERROR_LOG" ] && [ -s "$ERROR_LOG" ]; then
            echo ""
            echo "에러 로그:"
            echo "==========="
            tail -50 "$ERROR_LOG"
        fi
        ;;

    *)
        echo "JINXUS Daemon 관리"
        echo ""
        echo "사용법: $0 [command]"
        echo ""
        echo "Commands:"
        echo "  start     - Daemon 시작"
        echo "  stop      - Daemon 중지"
        echo "  restart   - Daemon 재시작"
        echo "  status    - 상태 확인"
        echo "  install   - Daemon 설치 (부팅 시 자동 시작)"
        echo "  uninstall - Daemon 제거"
        echo "  logs      - 로그 보기"
        exit 1
        ;;
esac
