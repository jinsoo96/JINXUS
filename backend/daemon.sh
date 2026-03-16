#!/bin/bash

# JINXUS Daemon 관리 스크립트
# Linux (systemd) / macOS (launchctl) 크로스 플랫폼 지원
# 사용법: ./daemon.sh [start|stop|restart|status|install|uninstall|logs]

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
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

# OS 감지
detect_os() {
    if [[ "$OSTYPE" == "darwin"* ]]; then
        echo "macos"
    else
        echo "linux"
    fi
}

OS=$(detect_os)

# macOS 설정
PLIST_NAME="com.jinxus.server"
PLIST_PATH="$HOME/Library/LaunchAgents/${PLIST_NAME}.plist"
SOURCE_PLIST="$SCRIPT_DIR/daemon/jinxus.plist"

# Linux systemd 설정
SERVICE_NAME="jinxus"
SERVICE_FILE="$HOME/.config/systemd/user/${SERVICE_NAME}.service"

ensure_docker() {
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
}

case "$1" in
    start)
        echo "JINXUS Daemon 시작 중..."
        ensure_docker

        if [[ "$OS" == "macos" ]]; then
            if [ -f "$PLIST_PATH" ]; then
                launchctl load "$PLIST_PATH" 2>/dev/null || true
                launchctl start "$PLIST_NAME" 2>/dev/null || true
            else
                print_error "Daemon 설치되지 않음. './daemon.sh install' 먼저 실행"
                exit 1
            fi
        else
            if [ -f "$SERVICE_FILE" ]; then
                systemctl --user start "$SERVICE_NAME"
            else
                print_error "Daemon 설치되지 않음. './daemon.sh install' 먼저 실행"
                exit 1
            fi
        fi

        sleep 3
        if curl -s http://localhost:19000/status > /dev/null 2>&1; then
            print_status "JINXUS Daemon 시작됨 (포트 19000)"
        else
            print_warning "서버 시작 중... 잠시 후 확인"
        fi
        ;;

    stop)
        echo "JINXUS Daemon 중지 중..."

        if [[ "$OS" == "macos" ]]; then
            if [ -f "$PLIST_PATH" ]; then
                launchctl stop "$PLIST_NAME" 2>/dev/null || true
                launchctl unload "$PLIST_PATH" 2>/dev/null || true
                print_status "JINXUS Daemon 중지됨"
            else
                pkill -f "python.*main.py" 2>/dev/null || true
                print_status "JINXUS 프로세스 종료됨"
            fi
        else
            if [ -f "$SERVICE_FILE" ]; then
                systemctl --user stop "$SERVICE_NAME" 2>/dev/null || true
                print_status "JINXUS Daemon 중지됨"
            else
                pkill -f "python.*main.py" 2>/dev/null || true
                print_status "JINXUS 프로세스 종료됨"
            fi
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

        # OS 표시
        echo "플랫폼: $OS"
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
        if [[ "$OS" == "macos" ]]; then
            if [ -f "$PLIST_PATH" ]; then
                print_status "Daemon 설치됨 (macOS launchctl)"
            else
                print_warning "Daemon 미설치 ('./daemon.sh install'로 설치)"
            fi
        else
            if [ -f "$SERVICE_FILE" ]; then
                print_status "Daemon 설치됨 (Linux systemd)"
                systemctl --user status "$SERVICE_NAME" --no-pager 2>/dev/null || true
            else
                print_warning "Daemon 미설치 ('./daemon.sh install'로 설치)"
            fi
        fi
        ;;

    install)
        echo "JINXUS Daemon 설치 중... (플랫폼: $OS)"

        if [[ "$OS" == "macos" ]]; then
            # macOS: LaunchAgents
            mkdir -p "$HOME/Library/LaunchAgents"

            if [ -f "$SOURCE_PLIST" ]; then
                sed "s|/Users/jinsookim/Desktop/JINXUS|$SCRIPT_DIR|g" "$SOURCE_PLIST" > "$PLIST_PATH"
                chmod 644 "$PLIST_PATH"
                print_status "Daemon 설치 완료 (macOS launchctl)"
            else
                print_error "plist 템플릿 파일 없음: $SOURCE_PLIST"
                exit 1
            fi
        else
            # Linux: systemd user service
            mkdir -p "$HOME/.config/systemd/user"

            # Python 경로 탐색
            PYTHON_BIN="$SCRIPT_DIR/.venv/bin/python3"
            if [ ! -f "$PYTHON_BIN" ]; then
                PYTHON_BIN=$(which python3)
            fi

            cat > "$SERVICE_FILE" << EOF
[Unit]
Description=JINXUS AI Assistant Backend
After=network.target docker.service

[Service]
Type=simple
WorkingDirectory=$SCRIPT_DIR
ExecStart=$PYTHON_BIN -m uvicorn jinxus.api.server:app --host 0.0.0.0 --port 19000
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
Environment=PATH=$SCRIPT_DIR/.venv/bin:/usr/local/bin:/usr/bin:/bin
Environment=PYTHONUNBUFFERED=1
EnvironmentFile=-$SCRIPT_DIR/.env

[Install]
WantedBy=default.target
EOF

            systemctl --user daemon-reload
            systemctl --user enable "$SERVICE_NAME"
            print_status "Daemon 설치 완료 (Linux systemd)"
            echo ""
            echo "부팅 시 자동 시작을 위해 다음 명령 실행:"
            echo "  sudo loginctl enable-linger $USER"
        fi

        echo ""
        echo "사용법:"
        echo "  ./daemon.sh start   - 시작"
        echo "  ./daemon.sh stop    - 중지"
        echo "  ./daemon.sh status  - 상태 확인"
        echo "  ./daemon.sh logs    - 로그 보기"
        ;;

    uninstall)
        echo "JINXUS Daemon 제거 중..."

        # 먼저 중지
        $0 stop 2>/dev/null || true

        if [[ "$OS" == "macos" ]]; then
            if [ -f "$PLIST_PATH" ]; then
                rm -f "$PLIST_PATH"
                print_status "Daemon 제거 완료 (macOS)"
            else
                print_warning "이미 제거됨"
            fi
        else
            if [ -f "$SERVICE_FILE" ]; then
                systemctl --user disable "$SERVICE_NAME" 2>/dev/null || true
                rm -f "$SERVICE_FILE"
                systemctl --user daemon-reload
                print_status "Daemon 제거 완료 (Linux systemd)"
            else
                print_warning "이미 제거됨"
            fi
        fi
        ;;

    logs)
        echo "JINXUS Daemon 로그:"
        echo "===================="

        if [[ "$OS" == "linux" ]] && [ -f "$SERVICE_FILE" ]; then
            # systemd 로그 우선 표시
            journalctl --user -u "$SERVICE_NAME" -n 100 --no-pager 2>/dev/null || true
        fi

        if [ -f "$LOG_FILE" ]; then
            echo ""
            echo "--- 파일 로그 ($LOG_FILE) ---"
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
        echo "JINXUS Daemon 관리 (플랫폼: $OS)"
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
