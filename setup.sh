#!/bin/bash

# JINXUS 자동 설치 스크립트
# 사용법: chmod +x setup.sh && ./setup.sh

set -e

echo "
╔═══════════════════════════════════════════════════════════╗
║                   JINXUS Setup Script                      ║
║         Multi-Agent AI Assistant System                    ║
╚═══════════════════════════════════════════════════════════╝
"

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 함수: 성공 메시지
success() {
    echo -e "${GREEN}✓ $1${NC}"
}

# 함수: 경고 메시지
warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

# 함수: 에러 메시지
error() {
    echo -e "${RED}✗ $1${NC}"
}

# 함수: 설치 체크
check_command() {
    if command -v $1 &> /dev/null; then
        success "$1 설치됨"
        return 0
    else
        return 1
    fi
}

echo "📋 시스템 요구사항 확인 중..."
echo ""

# ===== 1. Homebrew 체크 (macOS) =====
if [[ "$OSTYPE" == "darwin"* ]]; then
    if ! check_command brew; then
        warning "Homebrew 미설치. 설치 중..."
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
        success "Homebrew 설치 완료"
    fi
fi

# ===== 2. Python 체크 =====
if check_command python3; then
    PYTHON_VERSION=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1,2)
    if [[ $(echo "$PYTHON_VERSION >= 3.11" | bc -l) -eq 1 ]]; then
        success "Python $PYTHON_VERSION (3.11+ 필요)"
    else
        warning "Python $PYTHON_VERSION 버전이 낮습니다. 3.11+ 권장"
    fi
else
    error "Python3 미설치"
    if [[ "$OSTYPE" == "darwin"* ]]; then
        warning "설치 중: brew install python@3.11"
        brew install python@3.11
    else
        error "수동으로 Python 3.11+ 설치 필요"
        exit 1
    fi
fi

# ===== 3. Node.js 체크 =====
if check_command node; then
    NODE_VERSION=$(node --version | cut -d'v' -f2 | cut -d'.' -f1)
    if [[ $NODE_VERSION -ge 18 ]]; then
        success "Node.js v$NODE_VERSION (18+ 필요)"
    else
        warning "Node.js 버전이 낮습니다. 18+ 권장"
    fi
else
    error "Node.js 미설치"
    if [[ "$OSTYPE" == "darwin"* ]]; then
        warning "설치 중: brew install node"
        brew install node
    else
        error "수동으로 Node.js 18+ 설치 필요"
        exit 1
    fi
fi

# ===== 4. Docker 체크 =====
if check_command docker; then
    if docker info &> /dev/null; then
        success "Docker 실행 중"
    else
        warning "Docker가 설치됐지만 실행 중이 아닙니다"
        warning "Docker Desktop을 시작해주세요"
    fi
else
    error "Docker 미설치"
    warning "https://docker.com 에서 Docker Desktop 설치 필요"
fi

# ===== 5. tmux 설치 =====
echo ""
echo "📦 tmux 설치 확인 중..."
if ! check_command tmux; then
    warning "tmux 미설치. 설치 중..."
    if [[ "$OSTYPE" == "darwin"* ]]; then
        brew install tmux
    elif [[ -f /etc/debian_version ]]; then
        sudo apt-get update && sudo apt-get install -y tmux
    elif [[ -f /etc/redhat-release ]]; then
        sudo yum install -y tmux
    fi
    success "tmux 설치 완료"
fi

# ===== 6. Python 의존성 설치 =====
echo ""
echo "📦 Python 의존성 설치 중..."
pip3 install -r requirements.txt -q
success "Python 의존성 설치 완료"

# CLI 등록
pip3 install -e . -q
success "jinxus CLI 명령어 등록됨"

# ===== 7. Docker 컨테이너 실행 =====
echo ""
echo "🐳 Docker 컨테이너 확인 중..."

# Redis
if docker ps --format '{{.Names}}' | grep -q 'jinxus-redis'; then
    success "Redis 컨테이너 실행 중"
else
    if docker ps -a --format '{{.Names}}' | grep -q 'jinxus-redis'; then
        docker start jinxus-redis
        success "Redis 컨테이너 시작됨"
    else
        docker run -d --name jinxus-redis -p 6379:6379 redis:7-alpine
        success "Redis 컨테이너 생성 및 시작됨"
    fi
fi

# Qdrant
if docker ps --format '{{.Names}}' | grep -q 'jinxus-qdrant'; then
    success "Qdrant 컨테이너 실행 중"
else
    if docker ps -a --format '{{.Names}}' | grep -q 'jinxus-qdrant'; then
        docker start jinxus-qdrant
        success "Qdrant 컨테이너 시작됨"
    else
        docker run -d --name jinxus-qdrant -p 6333:6333 qdrant/qdrant
        success "Qdrant 컨테이너 생성 및 시작됨"
    fi
fi

# ===== 8. .env 파일 확인 =====
echo ""
echo "🔐 환경 설정 확인 중..."
if [ -f .env ]; then
    success ".env 파일 존재"
else
    if [ -f .env.example ]; then
        cp .env.example .env
        warning ".env 파일 생성됨 - API 키 설정 필요!"
        warning "vim .env 로 API 키를 입력해주세요"
    else
        error ".env.example 파일 없음"
    fi
fi

# ===== 9. 프론트엔드 의존성 =====
echo ""
echo "📦 프론트엔드 의존성 설치 중..."
cd frontend
npm install --silent
cd ..
success "프론트엔드 의존성 설치 완료"

# ===== 완료 =====
echo ""
echo "═══════════════════════════════════════════════════════════"
echo -e "${GREEN}✓ JINXUS 설치 완료!${NC}"
echo "═══════════════════════════════════════════════════════════"
echo ""
echo "📌 다음 단계:"
echo ""
echo "  1. .env 파일에 API 키 설정"
echo "     vim .env"
echo ""
echo "  2. 서버 실행 (24시간 운영)"
echo "     ./start.sh"
echo ""
echo "  3. 접속"
echo "     - 웹 UI: http://localhost:1818"
echo "     - API: http://localhost:9000"
echo ""
echo "  4. CLI 사용"
echo "     jinxus \"안녕?\""
echo ""
