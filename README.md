<div align="center">

<img src="JINXUS_IMG.png" alt="JINXUS" width="200"/>

# JINXUS

### Just Intelligent Nexus, eXecutes Under Supremacy

A hyper-personalized multi-agent AI assistant system with a virtual pixel office

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-green.svg)](https://fastapi.tiangolo.com)
[![Next.js](https://img.shields.io/badge/Next.js-14-black.svg)](https://nextjs.org)
[![Claude](https://img.shields.io/badge/Claude-Sonnet_4.6-orange.svg)](https://anthropic.com)
[![Version](https://img.shields.io/badge/Version-2.9.0-purple.svg)]()

**Web UI** | **Telegram** | **CLI** | **Daemon**

</div>

---

## Overview

JINXUS is a multi-agent AI system where a single orchestrator (JINXUS_CORE) manages 28+ specialized AI agents organized into teams. Each agent has a unique Korean persona, role, and personality. The system features a real-time pixel art virtual office where you can watch your AI employees work.

You interact with one central orchestrator and it handles everything behind the scenes: interpreting intent, decomposing complex tasks into subtasks, delegating work to the right specialist agents, collecting results, and delivering a unified response.

---

## Key Features

### Pixel Office Playground
- Canvas-based virtual office with 6 team rooms and a hallway
- 12x16 pixel art characters with 4-directional walking animation
- BFS pathfinding with smooth interpolation movement (48px/s)
- Tool-specific animations: typing, reading, thinking, searching
- Real-time SSE state updates (sub-second response)
- Speech bubbles, tool icons, and status indicators
- 50x30 tile office at 2x scale

### Multi-Agent Architecture
- **28 agents** across 6 teams: Executive, Engineering, Research, Operations, Marketing, Planning
- JINXUS_CORE orchestrates all sub-agents via LangGraph
- Dynamic hiring/firing via HR system
- Agent-specific tool access control (Tool Policy Engine)
- Automatic failover and task reassignment via `_REASSIGN_MAP`
- Progressive Disclosure: agents only see relevant tool guides
- Team fallback: if a specialist fails, the team lead handles it directly

### Intelligence
- **148 tools**: 19 native + 129 MCP (11 servers)
- Smart Router: auto-classifies messages into 4 execution paths (chat/task/background/project)
- DynamicToolExecutor with continuation support (auto-continues if max rounds are hit)
- ToolGraph v2: BM25 + wRRF + BFS tool discovery (~26 microseconds per query, zero API calls)
- Artifact Store: Redis-based inter-phase data sharing (files, code, data, reports)
- Review Loop: automatic code review followed by fix cycles (max 2 iterations)

### Autonomous Execution
- AutonomousRunner: up to 8 hours, 50 steps background execution
- Redis checkpoints for crash recovery
- Step-level timeouts (15 min) + LLM guardrails
- Task chaining with `depends_on` for building pipelines
- Pause/Resume support via `asyncio.Event`
- Telegram progress reports every 15 minutes

### Memory System
- 3-tier: Redis (short-term) + Qdrant (long-term vectors) + SQLite (metadata)
- Async Qdrant writes via `ThreadPoolExecutor(1)` with drain barrier
- Automatic importance scoring and TTL cleanup
- Semantic search across long-term memory
- Time-decay pruning with configurable half-life

### Frontend
- Next.js 14 + Zustand + TailwindCSS
- Real-time SSE streaming with smooth typing animation
- Team channels (Matrix/Synapse integration)
- Agent direct chat (bypasses JINXUS_CORE)
- Docker log panel (bottom, VSCode-style resizable)
- Dev notes management with CRUD
- Pixel Office Playground in Agents tab

---

## How It Works

### Smart Router

Every incoming message goes through a 2-stage classifier:

| Stage | How | Purpose |
|-------|-----|---------|
| Pattern Matching | Regex + keyword rules | Instant classification for obvious cases (~0ms) |
| LLM Fallback | Claude Haiku | Handles ambiguous messages (~200ms) |

The router classifies into 4 execution paths:

| Route | What Happens | Example |
|-------|-------------|---------|
| **Chat** | Direct LLM response, no tool use | "Hey, what's up?" |
| **Task** | Full agent graph: decompose, dispatch, aggregate | "Search today's weather in Seoul" |
| **Background** | AutonomousRunner: multi-step, hours-long, checkpoint-safe | "Deep-analyze this entire codebase" |
| **Project** | ProjectManager: phase DAG, parallel execution, review loops | "Build a web scraper with ML pipeline" |

### LangGraph Orchestration Pipeline

```
intake -> decompose -> dispatch -> aggregate -> reflect -> memory_write -> respond
```

- **Intake**: Parses intent, loads relevant memory context, identifies required capabilities
- **Decompose**: Breaks complex requests into atomic subtasks with dependency ordering
- **Dispatch**: Routes each subtask to the best-fit agent (with automatic reassignment on failure)
- **Aggregate**: Merges results from multiple agents into a coherent response
- **Reflect**: Self-evaluates quality, triggers retry if confidence is low
- **Memory Write**: Persists important context to 3-tier memory for future use
- **Respond**: Formats and streams the final answer via SSE

### Multi-Agent Hierarchy

```
JINXUS_CORE (central orchestrator)
 |
 +-- JX_CODER (Dev Lead)
 |    +-- JX_FRONTEND      -> React, Vue, CSS, UI/UX
 |    +-- JX_BACKEND       -> Python, APIs, databases, system design
 |    +-- JX_INFRA         -> Docker, CI/CD, configs, deployment
 |    +-- JX_REVIEWER      -> Code review, quality gates
 |    +-- JX_TESTER        -> Unit/integration tests
 |    +-- JX_AI_ENG        -> ML/AI engineering
 |    +-- JX_SECURITY      -> Security engineering
 |    +-- JX_DATA_ENG      -> Data engineering
 |    +-- JX_MOBILE        -> Mobile development
 |    +-- JX_ARCHITECT     -> System architecture
 |    +-- JX_PROMPT_ENG    -> Prompt engineering
 |
 +-- JX_RESEARCHER (Research Lead)
 |    +-- JX_WEB_SEARCHER  -> Naver, Brave, Tavily, RSS
 |    +-- JX_DEEP_READER   -> PDF analysis, image understanding
 |    +-- JX_FACT_CHECKER  -> Cross-validation, source scoring
 |
 +-- JX_MARKETING          -> JX_WRITER, JS_PERSONA, JX_SNS
 +-- JX_OPS, JX_ANALYST
 +-- JX_PRODUCT, JX_STRATEGY
 +-- JX_CTO, JX_COO, JX_CFO (C-Suite)
```

### DynamicToolExecutor

Agents use tools through the DynamicToolExecutor, which:

1. Injects only the tools the agent is allowed to use (via Tool Policy)
2. Sends the task + tool definitions to Claude's native tool_use API
3. Executes the selected tool, feeds the result back
4. Repeats for multi-step tool chains (up to `max_rounds` per agent)
5. Auto-continues if max rounds are hit mid-task

### Background Execution

| Feature | How It Works |
|---------|-------------|
| Redis Checkpointing | State saved after every step for crash recovery |
| Step Timeouts | Each step has a 15-minute timeout via `asyncio.wait_for` |
| LLM Guardrails | Separate Claude call validates each step's output |
| Pause / Resume | `asyncio.Event`-based control |
| Task Chaining | `depends_on` field for building execution pipelines |
| Real-time Progress | SSE streams `step_progress` events |
| Telegram Alerts | Progress every 15 min + instant completion/failure notification |
| Event Buffer | Events before client subscription are buffered and replayed |

### Project Manager

For large projects:

1. **LLM Decomposition** — Claude generates 2-15 phases with a dependency DAG
2. **DAG Execution** — Independent phases run in parallel (3 concurrent workers)
3. **Artifact Store** — Phases share outputs via Redis (files, code, data, reports)
4. **Review Loop** — Coding phases get auto-reviewed; issues trigger fix phases (max 2 iterations)
5. **SSE Streaming** — Phase-level and step-level progress in real-time

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | FastAPI + LangGraph, Python 3.11+ |
| **Frontend** | Next.js 14 + Zustand + TailwindCSS |
| **Memory** | Redis (short-term) + Qdrant (long-term vectors) + SQLite (metadata) |
| **AI** | Anthropic Claude API — Sonnet 4.6 (main) + Haiku 4.5 (classification/evaluation) |
| **Tools** | 19 native + 11 MCP servers (129 tools) + runtime MCP loader |
| **Channels** | Web UI, Telegram bot, CLI, background daemon |
| **Infra** | Docker Compose, PM2, multi-stage builds, volume-mounted source |

---

## Architecture

```
User -> JINXUS_CORE (Orchestrator)
         +-- JX_CODER (Dev Lead) -> JX_FRONTEND, JX_BACKEND, JX_INFRA, JX_REVIEWER, JX_TESTER, ...
         +-- JX_RESEARCHER (Research Lead) -> JX_WEB_SEARCHER, JX_DEEP_READER, JX_FACT_CHECKER
         +-- JX_MARKETING -> JX_WRITER, JS_PERSONA, JX_SNS
         +-- JX_OPS, JX_ANALYST
         +-- JX_PRODUCT, JX_STRATEGY
         +-- JX_CTO, JX_COO, JX_CFO (C-Suite)
```

---

## Tools

**19 Native Tools:**
Code executor, web search (Tavily), Naver search, weather, GitHub (REST + GraphQL), file manager, PDF reader, image analyzer, RSS reader, stock prices, community monitor, data processor (pandas), document generator (Word/PPT), scheduler, HR tool, system manager, self-modifier, prompt version manager

**11 MCP Servers (129 tools):**
Filesystem, Git, GitHub, Brave Search, web fetch, Playwright (browser automation), Firecrawl (web scraping), SQLite, Slack, Notion, sequential thinking, memory

MCP servers can be hot-loaded and removed at runtime via `POST /status/mcp/servers` without restart.

---

## API Reference

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/chat` | POST | SSE streaming chat (standard orchestration) |
| `/chat/smart` | POST | Auto-routed chat (Smart Router classifies and executes) |
| `/chat/agent/{name}` | POST | Direct agent chat (bypasses JINXUS_CORE) |
| `/chat/sync` | POST | Synchronous chat (blocks until complete) |
| `/task` | POST | Background task submission (autonomous mode) |
| `/task/{id}/stream` | GET | Task progress SSE stream |
| `/task/{id}/pause` | POST | Pause a running background task |
| `/task/{id}/resume` | POST | Resume a paused task |
| `/projects` | POST | Create multi-phase project |
| `/projects/{id}/start` | POST | Start project execution |
| `/projects/{id}/stream` | GET | Project progress SSE stream |
| `/projects/{id}/artifacts` | GET | Retrieve phase artifacts |
| `/processes` | POST/GET | Long-running process management |
| `/agents` | GET | Agent status, teams, capabilities |
| `/agents/runtime/stream` | GET | Real-time agent state SSE stream |
| `/status` | GET | System health, tool policies, MCP status |
| `/status/mcp/servers` | POST/DELETE | Add or remove MCP servers at runtime |
| `/memory/search` | POST | Semantic search across long-term memory |
| `/feedback` | POST | Submit task feedback for self-improvement |
| `/logs` | GET | Tool call logs, task history, metrics |

Interactive Swagger docs at `http://localhost:19000/docs`.

---

## Quick Start

### Prerequisites
- Docker and Docker Compose
- Anthropic API key
- Node.js 18+ (for frontend)

### Backend

```bash
cd backend
cp .env.example .env   # Add ANTHROPIC_API_KEY and other service keys
docker compose up -d   # Starts backend (FastAPI) + Redis + Qdrant
```

The backend uses volume-mounted source code. Edit files and run `docker compose restart jinxus` to apply changes. No rebuild needed unless `Dockerfile` changes. The `entrypoint.sh` automatically detects `requirements.txt` changes and runs `pip install` on restart.

### Frontend

```bash
cd frontend
bash dev.sh   # Detects package changes, installs deps, starts Next.js via pm2
```

HMR is enabled. Save a file and the browser updates instantly.

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

---

## Project Structure

```
backend/jinxus/
  agents/              # JINXUS_CORE orchestrator + sub-agents
    coding/            #   JX_CODER specialist team (11 agents)
    research/          #   JX_RESEARCHER specialist team (3 agents)
  api/routers/         # FastAPI route groups
  core/                # Orchestrator, background worker, autonomous runner,
                       # project manager, smart router, artifact store,
                       # review loop, subprocess manager, tool policy, tool graph
  memory/              # 3-tier memory: Redis + Qdrant + SQLite
  tools/               # 19 native tools + DynamicToolExecutor + MCP client
  hr/                  # Agent hiring/firing, team management
  config/              # Settings (env-driven), MCP server definitions
  channels/            # Telegram bot, CLI, daemon

frontend/src/
  components/tabs/     # UI tabs: Chat, Agents/Playground, Settings, Tools,
                       # Memory, Graph, Logs, Notes, Projects, CompanyChat
  lib/                 # Centralized API client, SSE parser, personas
  store/               # Zustand global state management
```

---

## Version History

| Version | Date | Highlights |
|---------|------|------------|
| **v2.9.0** | 2026-03-22 | Pixel Office Playground, UI overhaul, SSE agent streaming |
| v2.6.1 | 2026-03-19 | Matrix connection fixes, prompt engineer hiring |
| v2.6.0 | 2026-03-19 | 5 new dev team agents (27 total), agent count unification |
| v2.5.0 | 2026-03-19 | Next.js architecture fixes, bundle optimization (76% reduction) |
| v2.4.0 | 2026-03-19 | Persona system, HR/channel integration, production mode |
| v2.3.0 | 2026-03-16 | Smart Router, Artifact Store, Review Loop, Subprocess Manager |
| v2.1.0 | 2026-03-13 | Research team, SSE event buffer replay |
| v1.7.0 | 2026-03-12 | Background tasks: Redis checkpoints, pause/resume, task chaining |
| v1.6.0 | 2026-03-11 | Coding team specialists, continuation, progressive disclosure |
| v1.5.0 | 2026-03-09 | Docker multi-stage build, Tool Policy API, real-time tool logs |
| v1.4.0 | 2026-03-08 | Frontend overhaul, model fallback runner, session freshness |

See [docs/03_DEVELOP_STATUS.md](docs/03_DEVELOP_STATUS.md) for the full changelog.

---

## License

Private project. Not for redistribution.

---

<div align="center">

**Built by [jinsoo96](https://github.com/jinsoo96)**

Special thanks to [CocoRoF](https://github.com/CocoRoF) & [SonAIengine](https://github.com/SonAIengine)

</div>
