<div align="center">

<img src="JINXUS_IMG.png" alt="JINXUS" width="200"/>

# JINXUS

### Just Intelligent Nexus, eXecutes Under Supremacy

A hyper-personalized multi-agent AI assistant system where you give one command and an entire team of specialized AI agents collaborates to deliver the result.

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-green.svg)](https://fastapi.tiangolo.com)
[![Next.js](https://img.shields.io/badge/Next.js-14-black.svg)](https://nextjs.org)
[![Claude](https://img.shields.io/badge/Claude-Sonnet_4-orange.svg)](https://anthropic.com)
[![Version](https://img.shields.io/badge/Version-2.3.0-purple.svg)]()

**Web UI** | **Telegram** | **CLI** | **Daemon**

</div>

---

## What is JINXUS?

JINXUS is a **multi-agent AI orchestration system** built around a single principle: **you talk, agents work.**

You interact with one central orchestrator — **JINXUS_CORE** — and it handles everything behind the scenes. It interprets your intent, decomposes complex tasks into subtasks, delegates work to the right specialist agents, collects their results, and delivers a unified response. You never need to know which agent did what.

Whether it's writing code, researching a topic, generating documents, analyzing data, managing infrastructure, or running a multi-day project autonomously — JINXUS handles it end-to-end.

### What Can It Actually Do?

- **Write full applications** — "Build me a Flask REST API with auth and deploy it" triggers JX_CODER's team (frontend, backend, infra, reviewer, tester specialists) to scaffold, implement, review, test, and deploy.
- **Deep research** — "Find everything about Korea's 2026 AI policy changes" activates JX_RESEARCHER's team (web searcher, deep reader, fact checker) to search multiple sources, read PDFs, cross-validate facts, and compile a report.
- **Overnight autonomous projects** — Drop a big task and go to sleep. JINXUS runs it in the background for up to 8 hours with checkpoint recovery, sends Telegram progress updates every 15 minutes, and has the result ready when you wake up.
- **Manage infrastructure** — Start/stop/monitor long-running processes, check health, view logs, auto-restart on failure.
- **Generate documents** — Word docs, PowerPoint presentations, data analysis reports with pandas and visualization.
- **Browse the web** — Playwright-powered browser automation, web scraping via Firecrawl, RSS monitoring.
- **Remember everything** — 3-tier memory (Redis short-term, Qdrant vector long-term, SQLite metadata) so context persists across conversations and tasks.

---

## How It Works — Key Logic & Architecture

### 1. Smart Router (the brain at the gate)

Every incoming message goes through a **2-stage classifier** before any agent touches it:

| Stage | How | Purpose |
|-------|-----|---------|
| **Pattern Matching** | Regex + keyword rules | Instant classification for obvious cases (~0ms) |
| **LLM Fallback** | Claude Haiku | Handles ambiguous messages the patterns can't catch (~200ms) |

The router classifies into 4 execution paths:

| Route | What Happens | Example |
|-------|-------------|---------|
| **Chat** | Direct LLM response, no tool use | "Hey, what's up?" |
| **Task** | Full agent graph: decompose → dispatch → aggregate | "Search today's weather in Seoul" |
| **Background** | AutonomousRunner: multi-step, hours-long, checkpoint-safe | "Deep-analyze this entire codebase" |
| **Project** | ProjectManager: phase DAG, parallel execution, review loops | "Build a web scraper with ML pipeline" |

### 2. LangGraph Orchestration Pipeline

When a task reaches JINXUS_CORE, it flows through a **7-node directed graph**:

```
intake → decompose → dispatch → aggregate → reflect → memory_write → respond
```

- **Intake**: Parses intent, loads relevant memory context, identifies required capabilities
- **Decompose**: Breaks complex requests into atomic subtasks with dependency ordering
- **Dispatch**: Routes each subtask to the best-fit agent (with automatic reassignment on failure)
- **Aggregate**: Merges results from multiple agents into a coherent response
- **Reflect**: Self-evaluates quality, triggers retry if confidence is low
- **Memory Write**: Persists important context to 3-tier memory for future use
- **Respond**: Formats and streams the final answer via SSE

### 3. Multi-Agent Hierarchy (15 agents)

```
JINXUS_CORE (central orchestrator — the only agent you talk to)
 │
 ├── JX_CODER (coding team lead)
 │    ├── JX_FRONTEND    → React, Vue, CSS, UI/UX
 │    ├── JX_BACKEND     → Python, APIs, databases, system design
 │    ├── JX_INFRA       → Docker, CI/CD, configs, deployment
 │    ├── JX_REVIEWER    → Code review, quality gates, best practices
 │    └── JX_TESTER      → Unit tests, integration tests, test strategies
 │
 ├── JX_RESEARCHER (research team lead)
 │    ├── JX_WEB_SEARCHER  → Naver, Brave, Tavily, RSS, community forums
 │    ├── JX_DEEP_READER   → PDF analysis, image understanding, GitHub repos
 │    └── JX_FACT_CHECKER  → Cross-validation, source credibility scoring
 │
 ├── JX_WRITER     → Documents, reports, presentations (Word/PPT)
 ├── JX_ANALYST    → Data analysis (pandas), visualization, stock tracking
 ├── JX_OPS        → Infrastructure, deployment, automation, monitoring
 └── JS_PERSONA    → Personality layer, conversational style adaptation
```

**Key behaviors:**
- Each agent has a **Tool Policy** — a whitelist/blacklist controlling exactly which tools it can access
- **Progressive Disclosure** — agents only see tool descriptions relevant to their role, reducing confusion
- **Automatic reassignment** — if JX_CODER fails, `_REASSIGN_MAP` routes the task to JX_OPS or another capable agent
- **Team fallback** — if a specialist (e.g., JX_FRONTEND) fails, the team lead (JX_CODER) handles it directly

### 4. DynamicToolExecutor (how agents use tools)

Agents don't call tools directly. They go through the **DynamicToolExecutor**, which:

1. Injects only the tools the agent is allowed to use (via Tool Policy)
2. Sends the task + tool definitions to Claude's native **tool_use API**
3. Executes the tool Claude selects, feeds the result back
4. Repeats for multi-step tool chains (up to `max_rounds` per agent)
5. **Auto-continues** if max rounds are hit mid-task — seamlessly picks up where it left off

This means agents can chain 15+ tool calls in a single task without manual intervention.

### 5. ToolGraph v2 (instant tool discovery)

Before the DynamicToolExecutor runs, the system needs to know which tools are relevant. **ToolGraph v2** handles this:

- **BM25 text scoring** on tool names and descriptions
- **Weighted Reciprocal Rank Fusion (wRRF)** combining multiple signals
- **Graph BFS traversal** to find related tools (e.g., "github" → git, filesystem)
- **History demotion** to avoid re-suggesting recently failed tools
- Result: **~26 microseconds per query, zero API calls**

### 6. Autonomous Background Execution

For long-running tasks, the **AutonomousRunner** + **BackgroundWorker** system provides:

| Feature | How It Works |
|---------|-------------|
| **Redis Checkpointing** | State saved after every step → crash recovery without re-running completed work |
| **Step Timeouts** | Each step has a 10-minute timeout via `asyncio.wait_for` — no infinite hangs |
| **LLM Guardrails** | A separate Claude call validates each step's output before proceeding |
| **Pause / Resume** | `asyncio.Event`-based control — pause mid-execution, resume later |
| **Task Chaining** | `depends_on` field lets you build pipelines — Task B starts only after Task A completes |
| **Real-time Progress** | SSE streams `step_progress` events with `steps_completed / steps_total` |
| **Telegram Alerts** | Progress reports every 15 minutes + instant notification on completion/failure |
| **Event Buffer** | Events that fire before a client subscribes are buffered and replayed on connect |

Max runtime: **8 hours, 50 steps** per task.

### 7. Project Manager (multi-phase execution)

For large projects, the **ProjectManager** goes beyond simple task execution:

1. **LLM Decomposition** — Claude analyzes the project description and generates 2-15 phases with a dependency DAG
2. **DAG Execution** — Independent phases run in parallel (3 concurrent workers), dependent phases wait
3. **Artifact Store** — Phases share outputs via Redis (files, code blocks, data, reports). Auto-extracted from results, auto-injected into downstream phases
4. **Review Loop** — Every coding phase gets auto-reviewed. If issues are found, a fix phase is dynamically generated (max 2 iterations)
5. **SSE Streaming** — Phase-level and step-level progress streamed in real-time

### 8. 3-Tier Memory System

| Tier | Storage | Purpose | Retention |
|------|---------|---------|-----------|
| **Short-term** | Redis | Current conversation context, recent tool results | Session-scoped with TTL |
| **Long-term** | Qdrant (vector DB) | Semantic memory — searchable by meaning, not just keywords | Persistent, importance-scored |
| **Metadata** | SQLite | Task logs, metrics, tool call history, agent performance | Persistent |

Memory features:
- **Async writes** — `ThreadPoolExecutor(1)` ensures memory writes never block the main response
- **Importance scoring** — memories are scored and low-value entries are automatically pruned
- **Semantic search** — "What did we discuss about deployment?" retrieves relevant memories by meaning

### 9. 148+ Tools

**19 Native Tools:**
Code executor, web search (Tavily), Naver search, weather, GitHub (REST + GraphQL), file manager, PDF reader, image analyzer, RSS reader, stock prices, community monitor, data processor (pandas), document generator (Word/PPT), scheduler, HR tool, system manager, self-modifier, prompt version manager

**13 MCP Servers (130+ tools):**
Filesystem, Git, GitHub, Brave Search, web fetch, Playwright (browser automation), Firecrawl (web scraping), PostgreSQL, SQLite, Slack, Notion, sequential thinking, memory

MCP servers can be **hot-loaded and removed at runtime** via `POST /status/mcp/servers` — no restart needed.

### 10. Self-Improvement Loop

JINXUS gets better over time:
- **Feedback ingestion** — every task can receive user feedback via `/feedback`
- **Prompt A/B testing** — system prompts are versioned and tested against each other
- **Automatic rollback** — if a new prompt version regresses quality, it rolls back
- **Failure pattern learning** — repeated failures on similar tasks trigger prompt adjustments

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | FastAPI + LangGraph, Python 3.11+ |
| **Frontend** | Next.js 14 + Zustand + TailwindCSS |
| **Memory** | Redis (short-term) + Qdrant (long-term vectors) + SQLite (metadata) |
| **AI** | Anthropic Claude API — Sonnet 4 (main) + Haiku 4.5 (classification/evaluation) |
| **Tools** | 19 native + 13 MCP servers (130+ tools) + runtime MCP loader |
| **Channels** | Web UI, Telegram bot, CLI, background daemon |
| **Infra** | Docker Compose, multi-stage builds, volume-mounted source for hot reload |

---

## API Reference

18 endpoint groups:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/chat` | POST | SSE streaming chat (standard orchestration) |
| `/chat/smart` | POST | Auto-routed chat — Smart Router classifies and executes |
| `/chat/agent/{name}` | POST | Direct agent chat (bypasses JINXUS_CORE) |
| `/chat/sync` | POST | Synchronous chat (blocks until complete) |
| `/task` | POST | Background task submission (autonomous mode) |
| `/task/{id}/stream` | GET | Task progress SSE stream |
| `/task/{id}/pause` | POST | Pause a running background task |
| `/task/{id}/resume` | POST | Resume a paused task |
| `/projects` | POST | Create multi-phase project (LLM decomposes into phases) |
| `/projects/{id}/start` | POST | Start project execution |
| `/projects/{id}/stream` | GET | Project progress SSE stream |
| `/projects/{id}/artifacts` | GET | Retrieve phase artifacts |
| `/processes` | POST/GET | Long-running process management |
| `/processes/{id}/health` | GET | Process health check (uptime, HTTP status) |
| `/agents` | GET | Agent status, teams, capabilities, tool counts |
| `/status` | GET | System health, tool policies, MCP server status |
| `/status/mcp/servers` | POST/DELETE | Add or remove MCP servers at runtime |
| `/memory/search` | POST | Semantic search across long-term memory |
| `/feedback` | POST | Submit task feedback for self-improvement |
| `/logs` | GET | Tool call logs, task history, metrics |

Interactive Swagger docs available at `http://localhost:19000/docs`.

---

## Quick Start

### Prerequisites
- Docker & Docker Compose
- Anthropic API key
- Node.js 18+ (for frontend)

### Backend

```bash
cd backend
cp .env.example .env   # Add ANTHROPIC_API_KEY and other service keys
docker compose up -d   # Starts backend (FastAPI) + Redis + Qdrant
```

The backend uses **volume-mounted source code** — edit files and `docker compose restart jinxus` to apply changes. No rebuild needed unless `Dockerfile` changes. The `entrypoint.sh` automatically detects `requirements.txt` changes and runs `pip install` on restart.

### Frontend

```bash
cd frontend
bash dev.sh   # Detects package changes, installs deps, starts Next.js dev server via pm2
```

HMR (Hot Module Replacement) is enabled — save a file and the browser updates instantly.

### Access

| Service | URL |
|---------|-----|
| Web UI | `http://localhost:5000` |
| Backend API | `http://localhost:19000` |
| Swagger Docs | `http://localhost:19000/docs` |
| Telegram | Configure `TELEGRAM_BOT_TOKEN` in `.env` |

---

## Telegram Commands

| Command | Action |
|---------|--------|
| `/start` | Begin conversation |
| `/status` | System status overview |
| `/agents` | List all agents and their states |
| `/auto <task>` | Run autonomous multi-step execution |
| `/bg <task>` | Submit background task |
| `/pause` | Pause the running task |
| `/resume` | Resume a paused task |
| `/cancel` | Cancel the running task |

Background tasks send progress reports via Telegram every 15 minutes and notify immediately on completion or failure.

---

## Project Structure

```
backend/jinxus/
  agents/              # JINXUS_CORE orchestrator + 6 sub-agents
    coding/            #   JX_CODER specialist team (5 agents)
    research/          #   JX_RESEARCHER specialist team (3 agents)
  api/routers/         # FastAPI route groups (chat, tasks, projects, processes, agents, status, logs)
  core/                # Orchestrator, background worker, autonomous runner,
                       # project manager, smart router, artifact store,
                       # review loop, subprocess manager, tool policy,
                       # tool graph, model router, context guard, session freshness
  memory/              # 3-tier memory: Redis (short) + Qdrant (long) + SQLite (meta)
  tools/               # 19 native tools + DynamicToolExecutor + MCP client
  hr/                  # Agent hiring/firing, team management, factory
  config/              # Settings (env-driven), MCP server definitions
  channels/            # Telegram bot, CLI, daemon (24h background service)

frontend/src/
  components/tabs/     # UI tabs: Chat, Dashboard, Agents, Graph,
                       # Tools, Memory, Settings, Logs, Notes, Projects
  lib/                 # Centralized API client, SSE parser, smooth streaming utilities
  store/               # Zustand global state management
```

---

## Version History

| Version | Date | Highlights |
|---------|------|------------|
| **v2.3.0** | 2026-03-16 | Smart Router, Artifact Store, Review-Fix Loop, Subprocess Manager, ProjectManager |
| v2.2.0 | 2026-03-14 | Performance patches, memory leak fixes, MCP dynamic loader with auto-annotation |
| v2.1.0 | 2026-03-13 | JX_RESEARCHER specialist team (3 experts), SSE event buffer replay |
| v1.7.0 | 2026-03-12 | Background work: Redis checkpoints, real progress, pause/resume, task chaining |
| v1.6.0 | 2026-03-11 | JX_CODER specialist team (5 experts), continuation, progressive disclosure |
| v1.5.0 | 2026-03-09 | Docker multi-stage build, Tool Policy API, real-time tool call logs |
| v1.4.0 | 2026-03-08 | Frontend overhaul, model fallback runner, session freshness policy |

See [docs/03_DEVELOP_STATUS.md](docs/03_DEVELOP_STATUS.md) for the full changelog.

---

## License

Private project. Not for redistribution.

---

<div align="center">

**Built by [jinsoo96](https://github.com/jinsoo96)**

Special thanks to [CocoRoF](https://github.com/CocoRoF) & [SonAIengine](https://github.com/SonAIengine)

</div>
