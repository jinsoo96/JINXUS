FROM python:3.11-slim

WORKDIR /app

# 시스템 의존성 + Node.js 설치
RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    git \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Python 의존성
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# MCP 패키지 글로벌 설치
RUN npm install -g \
    @modelcontextprotocol/server-memory \
    @modelcontextprotocol/server-filesystem \
    @modelcontextprotocol/server-brave-search \
    @modelcontextprotocol/server-github \
    @modelcontextprotocol/server-sequential-thinking \
    mcp-fetch-server \
    mcp-git \
    mcp-sqlite-server \
    @playwright/mcp

# Playwright 브라우저 설치 (의존성 포함)
RUN npx playwright install --with-deps chromium

# 소스 코드 복사
COPY . .

# 데이터 디렉토리 생성
RUN mkdir -p /app/data/logs

# 포트
EXPOSE 19000

# 실행
CMD ["python", "main.py"]
