# ===== Stage 1: Builder =====
FROM python:3.11-slim AS builder

WORKDIR /build

# 빌드 도구 설치 + Node.js
RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    git \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Python wheels 빌드
COPY requirements.txt .
RUN pip wheel --no-cache-dir --wheel-dir=/build/wheels -r requirements.txt

# MCP 패키지 설치 (나중에 복사할 글로벌 경로)
RUN npm install -g --prefix /build/npm \
    @modelcontextprotocol/server-memory \
    @modelcontextprotocol/server-filesystem \
    @modelcontextprotocol/server-brave-search \
    @modelcontextprotocol/server-github \
    @modelcontextprotocol/server-sequential-thinking \
    mcp-fetch-server \
    mcp-git \
    mcp-sqlite-server \
    @playwright/mcp

# ===== Stage 2: Runtime =====
FROM python:3.11-slim

WORKDIR /app

# 타임존 KST 설정
ENV TZ=Asia/Seoul
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# 런타임 의존성: Node.js + curl (healthcheck용) + git (mcp-git 런타임)
RUN apt-get update && apt-get install -y \
    curl \
    git \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Python 패키지 설치 (빌드된 wheels 사용, 컴파일러 불필요)
COPY --from=builder /build/wheels /tmp/wheels
COPY requirements.txt .
RUN pip install --no-cache-dir --no-index --find-links=/tmp/wheels -r requirements.txt \
    && rm -rf /tmp/wheels

# MCP 패키지 복사
COPY --from=builder /build/npm /usr/local
ENV NODE_PATH=/usr/local/lib/node_modules

# Playwright 브라우저 설치 (의존성 포함, 런타임 필요)
RUN npx playwright install --with-deps chromium

# 소스 코드 복사
COPY . .

# 데이터 디렉토리 생성
RUN mkdir -p /app/data/logs

# 포트
EXPOSE 19000

# 실행
CMD ["python", "main.py"]
