# ===== Stage 1: Builder =====
FROM python:3.11-slim AS builder

WORKDIR /build

# 빌드 도구 + Node.js 22 (firecrawl 등 최신 MCP 호환)
RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    git \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Python wheels 빌드
COPY requirements.txt .
RUN pip wheel --no-cache-dir --wheel-dir=/build/wheels -r requirements.txt

# MCP npm 패키지 사전 설치 (npx -y 대기 시간 제거)
RUN npm install -g --prefix /build/npm \
    @modelcontextprotocol/server-memory \
    @modelcontextprotocol/server-filesystem \
    @modelcontextprotocol/server-brave-search \
    @modelcontextprotocol/server-github \
    @modelcontextprotocol/server-sequential-thinking \
    @kazuph/mcp-fetch \
    mcp-git \
    mcp-sqlite-server \
    @playwright/mcp \
    @notionhq/notion-mcp-server \
    firecrawl-mcp

# ===== Stage 2: Runtime =====
FROM python:3.11-slim

WORKDIR /app

# 타임존 KST 설정
ENV TZ=Asia/Seoul
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# 런타임 의존성: Node.js 22 + curl (healthcheck) + git (mcp-git)
RUN apt-get update && apt-get install -y \
    curl \
    git \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Python 패키지 설치
COPY --from=builder /build/wheels /tmp/wheels
COPY requirements.txt .
RUN pip install --no-cache-dir --no-index --find-links=/tmp/wheels -r requirements.txt \
    && rm -rf /tmp/wheels

# MCP 패키지 복사
COPY --from=builder /build/npm /usr/local
ENV NODE_PATH=/usr/local/lib/node_modules

# Playwright 브라우저 설치
RUN npx playwright install --with-deps chromium

# 소스 코드 복사
COPY . .

# 데이터 디렉토리
RUN mkdir -p /app/data/logs

# 엔트리포인트 (requirements.txt 변경 시 자동 pip install)
RUN chmod +x /app/entrypoint.sh

EXPOSE 19000

ENTRYPOINT ["/app/entrypoint.sh"]
