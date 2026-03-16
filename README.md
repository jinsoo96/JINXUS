<div align="center">

<img src="JINXUS_IMG.png" alt="JINXUS" width="200"/>

# JINXUS

### Just Intelligent Nexus, eXecutes Under Supremacy

A hyper-personalized multi-agent AI system that turns a single command into a fully orchestrated operation.

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-green.svg)](https://fastapi.tiangolo.com)
[![Next.js](https://img.shields.io/badge/Next.js-14-black.svg)](https://nextjs.org)
[![Claude](https://img.shields.io/badge/Claude-Sonnet_4-orange.svg)](https://anthropic.com)
[![Version](https://img.shields.io/badge/Version-2.3.0-purple.svg)]()

**Web UI** | **Telegram** | **CLI** | **Daemon**

</div>

---

## What JINXUS Does

You talk to **one agent** (JINXUS_CORE). It interprets your command, breaks it into subtasks, delegates to specialist agents, aggregates results, and reports back. You never deal with the internals.

```
You: "Build me a community language-style learning bot at /home/user/talker"

JINXUS:
  1. Decomposes into 12 phases (project structure, crawler, NLP pipeline, tests...)
  2. Executes phases in dependency order, parallelizing where possible
  3. Auto-reviews coding output, creates fix iterations if issues found
  4. Shares artifacts (files, code, reports) between phases
  5. Streams real-time progress via SSE
  6. Delivers completed project
```

---

## Core Capabilities

### Smart Routing

Every message is automatically classified and routed to the optimal execution path:

| You Say | Route | What Happens |
|---------|-------|-------------|
| "Hey, what's up?" | **Chat** | Direct LLM response (~1s) |
| "Search today's weather in Seoul" | **Task** | Agent graph: decompose → dispatch → aggregate (~10s) |
| "Deep-analyze this entire codebase" | **Background** | AutonomousRunner: multi-step, hours-long, checkpoint-safe |
| "Build a web scraper with ML pipeline" | **Project** | ProjectManager: phase DAG, parallel execution, review loops |

No manual routing needed. The Smart Router uses 2-stage classification (pattern matching + LLM fallback).

### Autonomous Project Execution

Give JINXUS a big project and walk away:

- **LLM-driven decomposition** into 2-15 phases with dependency DAG
- **Parallel execution** of independent phases (3 concurrent workers)
- **Auto code review** on coding phases with fix iteration (max 2 rounds)
- **Artifact sharing** between phases (files, code blocks, data, reports via Redis)
- **Redis checkpointing** for crash recovery
- **Pause / resume / cancel** at any time
- **Real-time SSE streaming** of phase-level and step-level progress
- **Telegram notifications** on milestones and completion

### 15 Agents, One Orchestrator

```
JINXUS_CORE (orchestrator - the only agent you talk to)
 |
 |-- JX_CODER (coding lead)
 |    |-- JX_FRONTEND    (React, Vue, CSS)
 |    |-- JX_BACKEND     (Python, APIs, databases)
 |    |-- JX_INFRA       (Docker, CI/CD, configs)
 |    |-- JX_REVIEWER    (code review, quality checks)
 |    +-- JX_TESTER      (unit tests, integration tests)
 |
 |-- JX_RESEARCHER (research lead)
 |    |-- JX_WEB_SEARCHER  (Naver, Brave, RSS, community)
 |    |-- JX_DEEP_READER   (PDF, images, GitHub analysis)
 |    +-- JX_FACT_CHECKER  (cross-validation, source credibility)
 |
 |-- JX_WRITER     (documents, reports, presentations)
 |-- JX_ANALYST    (data analysis, visualization, stocks)
 |-- JX_OPS        (infrastructure, deployment, automation)
 +-- JS_PERSONA    (personality, conversational style)
```

Each agent has its own **Tool Policy** (whitelist/blacklist), max tool rounds, and continuation limits. Failed agents are automatically **reassigned** to alternates via `_REASSIGN_MAP`.

### 148+ Tools

**19 native tools:**
code executor, web search (Tavily), Naver search, weather, GitHub (REST + GraphQL), file manager, PDF reader, image analyzer, RSS reader, stock prices, community monitor, data processor (pandas), document generator (Word/PPT), scheduler, HR tool, system manager, self-modifier, prompt version manager

**13 MCP servers (130+ tools):**
filesystem, git, GitHub, Brave Search, web fetch, Playwright (browser automation), Firecrawl, PostgreSQL, SQLite, Slack, Notion, sequential thinking, memory

MCP servers can be **added/removed at runtime** via `POST /status/mcp/servers`.

Tool selection uses Claude's native **tool_use API** with **Progressive Disclosure** -- each agent only sees the tools it's allowed to use.

### Process Management

Start, stop, monitor, and auto-restart long-running processes:

```bash
# Start a dev server
POST /processes { "id": "dev", "name": "dev-server", "command": "npm run dev", "port": 3000, "auto_restart": true }

# Health check
GET /processes/dev/health  # { "healthy": true, "uptime_s": 3600, "http_healthy": true }

# View logs
GET /processes/dev/logs?lines=100
```

Security: command blacklist + directory whitelist. Max 3 auto-restarts.

---

## Architecture

| Layer | Tech |
|-------|------|
| **Backend** | FastAPI + LangGraph, Python 3.11+ |
| **Frontend** | Next.js 14 + Zustand + TailwindCSS |
| **Memory** | Redis (short-term) + Qdrant (long-term vectors) + SQLite (metadata) |
| **AI** | Anthropic Claude API (model router: sonnet for main, haiku for classification) |
| **Tools** | 19 native + 13 MCP servers (130+ tools) + runtime MCP loader |
| **Channels** | Web UI, Telegram bot, CLI, daemon |

### Key Systems

| System | What It Does |
|--------|-------------|
| **LangGraph Orchestration** | intake -> decompose -> dispatch -> aggregate -> reflect -> memory_write -> respond |
| **3-Tier Memory** | Redis short-term (conversation), Qdrant long-term (semantic search), SQLite metadata (task logs, metrics) |
| **ToolGraph v2** | BM25 + weighted RRF + graph BFS for tool discovery (~26us/query, zero API calls) |
| **DynamicToolExecutor** | Claude tool_use with auto-continuation when max rounds reached |
| **AutonomousRunner** | Multi-step execution with Redis checkpoints, per-step timeouts, guardrail validation, pause/resume |
| **BackgroundWorker** | 3 concurrent workers, task chaining (depends_on), conditional branching, SSE event buffer replay |
| **ProjectManager** | LLM phase decomposition, DAG execution, artifact store, review-fix loop |
| **Smart Router** | 2-stage classification: pattern matching -> LLM fallback (chat/task/background/project) |
| **Review Loop** | Auto code review on completed phases, fix phase generation, max 2 iterations |
| **Artifact Store** | Redis-based cross-phase sharing: files, code, data, reports. Auto-extraction from results |
| **Subprocess Manager** | Long-running process lifecycle: start/stop/restart/health/logs |
| **HR System** | Dynamic agent hiring/firing, specialist team delegation, failure reassignment |
| **Self-Improvement** | Feedback loop, A/B prompt testing, automatic rollback on regression |

---

## API

13 route groups under `/api`:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/chat` | POST | SSE streaming chat (standard) |
| `/chat/smart` | POST | **Auto-routed** chat (chat/task/background/project) |
| `/chat/agent/{name}` | POST | Direct agent chat (bypass JINXUS_CORE) |
| `/chat/sync` | POST | Synchronous chat (no streaming) |
| `/task` | POST | Background task submission (autonomous mode) |
| `/task/{id}/stream` | GET | Task progress SSE |
| `/projects` | POST | Multi-phase project creation (LLM decomposition) |
| `/projects/{id}/start` | POST | Start project execution |
| `/projects/{id}/stream` | GET | Project progress SSE |
| `/projects/{id}/artifacts` | GET | Phase artifact retrieval |
| `/processes` | POST/GET | Long-running process management |
| `/processes/{id}/health` | GET | Process health check |
| `/agents` | GET | Agent status, teams, capabilities |
| `/status` | GET | System status, tool policies, MCP servers |
| `/status/mcp/servers` | POST/DELETE | Runtime MCP server management |
| `/memory/search` | POST | Semantic memory search |
| `/feedback` | POST | Task feedback for self-improvement |
| `/logs` | GET | Tool call and task logs |

Full Swagger docs at `http://localhost:19000/docs`.

---

## Quick Start

### Prerequisites
- Docker & Docker Compose
- Anthropic API key
- Node.js 18+ (for frontend)

### Backend

```bash
cd backend
cp .env.example .env   # Add your ANTHROPIC_API_KEY + other keys
docker compose up -d   # Starts backend + Redis + Qdrant
```

### Frontend

```bash
cd frontend
bash dev.sh            # Auto-installs deps + starts Next.js dev server
```

### Access

| Service | URL |
|---------|-----|
| Web UI | http://localhost:5000 |
| Backend API | http://localhost:19000 |
| Swagger Docs | http://localhost:19000/docs |
| Telegram | Configure `TELEGRAM_BOT_TOKEN` in `.env` |

---

## Telegram Commands

| Command | Action |
|---------|--------|
| `/start` | Begin conversation |
| `/status` | System status |
| `/agents` | Agent list and states |
| `/auto <task>` | Autonomous multi-step execution |
| `/bg <task>` | Background task |
| `/pause` | Pause running task |
| `/resume` | Resume paused task |
| `/cancel` | Cancel running task |

---

## Project Structure

```
backend/jinxus/
  agents/              # JINXUS_CORE + 6 sub-agents + specialist teams
    coding/            #   JX_CODER team (5 specialists)
    research/          #   JX_RESEARCHER team (3 specialists)
  api/routers/         # 13 FastAPI route groups
  core/                # Orchestrator, background worker, autonomous runner,
                       # project manager, smart router, artifact store,
                       # review loop, subprocess manager, tool policy/graph,
                       # model router, context guard, session freshness
  memory/              # 3-tier: Redis short-term, Qdrant long-term, SQLite meta
  tools/               # 19 native tools + dynamic executor + MCP client
  hr/                  # Agent hiring/firing/team management
  config/              # Settings (env-driven), MCP server definitions
  channels/            # Telegram bot, CLI, daemon

frontend/src/
  components/tabs/     # 10 UI tabs: Chat, Dashboard, Agents, Graph,
                       # Tools, Memory, Settings, Logs, Notes, Projects
  lib/                 # API client, SSE parser, smooth streaming
  store/               # Zustand state management
```

---

## Version History

| Version | Date | Highlights |
|---------|------|------------|
| **v2.3.0** | 2026-03-16 | Smart Router, Artifact Store, Review-Fix Loop, Subprocess Manager |
| v2.2.0 | 2026-03-14 | Performance patches, memory leak fixes, MCP dynamic loader |
| v2.1.0 | 2026-03-13 | JX_RESEARCHER specialist team, SSE event buffer |
| v1.7.0 | 2026-03-12 | Background work: checkpoints, progress, pause/resume, task chaining |
| v1.6.0 | 2026-03-11 | JX_CODER specialist team, continuation, progressive disclosure |
| v1.5.0 | 2026-03-09 | Docker multi-stage, Tool Policy API, real-time tool logs |
| v1.4.0 | 2026-03-08 | Frontend overhaul, model fallback, session freshness |

See [docs/03_DEVELOP_STATUS.md](docs/03_DEVELOP_STATUS.md) for full changelog.

---

## License

Private project. Not for redistribution.

---

<div align="center">

**Built by [jinsoo96](https://github.com/jinsoo96)**

Special thanks to [CocoRoF](https://github.com/CocoRoF) & [SonAIengine](https://github.com/SonAIengine)

</div>
