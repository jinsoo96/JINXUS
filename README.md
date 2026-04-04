<div align="center">

<img src="JINXUS_IMG.png" alt="JINXUS" width="200"/>

# JINXUS

### Just Intelligent Nexus, eXecutes Under Supremacy

A hyper-personalized multi-agent AI assistant with a virtual pixel office

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-green.svg)](https://fastapi.tiangolo.com)
[![Next.js](https://img.shields.io/badge/Next.js-14-black.svg)](https://nextjs.org)
[![Claude](https://img.shields.io/badge/Claude-Sonnet_4.6-orange.svg)](https://anthropic.com)
[![Version](https://img.shields.io/badge/Version-4.1.1-purple.svg)]()

**Web UI** | **Telegram** | **CLI** | **Daemon**

</div>

---

## Overview

JINXUS is a multi-agent AI system where a single orchestrator (JINXUS_CORE) manages 28+ specialized AI agents organized into a realistic Korean IT company structure. Each agent has a unique persona with name, personality, MBTI, and work style. The system features a real-time pixel art virtual office where you can watch your AI employees work, chat, and collaborate.

You talk to one central orchestrator. It handles everything: interpreting intent, decomposing complex tasks, delegating to specialist agents, collecting results, and delivering a unified response.

The system includes a **Shared Whiteboard** where agents autonomously discover new information, propose actions, and execute missions — plus a **Trigger Engine** and **Autopilot UI** for managing agent autonomy levels, routines, budgets, and inter-agent communication.

---

## Key Features

### Pixel Office (Generative Agents-inspired)
- **60x40 tile map** with indoor offices, hallways, and outdoor areas (smoking area, garden, terrace, parking lot)
- **16x24 chibi sprites** with 2-head proportions, team-colored uniforms, and 12 hair variations
- **Camera/viewport system** with drag-to-scroll and wheel-to-zoom
- **BFS pathfinding** with smooth interpolation movement
- **28+ POIs** (coffee machine, whiteboard, printer, vending machine, benches, etc.) with state tracking
- **Shared Whiteboard** in the hallway — agents visit, discover new memos, and auto-generate missions
- **Per-agent daily schedules** based on rank and team
- **Emoji activity display** above character heads
- **Spontaneous agent chat** with 92 Korean dialogue templates (zero API cost)
- **Global mute** ("shut up" mode) silences idle chatter across all tabs while missions run normally
- Tool-specific animations: typing, reading, thinking, searching
- Real-time SSE state updates from backend

### Multi-Agent Architecture
- **28 agents** across 6 teams: Executive, Development, Platform, Product, Marketing, Biz Support
- Realistic Korean IT company structure (CTO, team leads, senior engineers, etc.)
- JINXUS_CORE orchestrates all sub-agents via LangGraph
- Dynamic hiring/firing via HR system (auto-updates playground layout)
- Agent-specific tool access control (Tool Policy Engine)
- Automatic failover and task reassignment
- Team fallback: if a specialist fails, the team lead handles it directly

### Mission System
- **4 mission types**: QUICK (instant), STANDARD (minutes), EPIC (hours), RAID (multi-agent)
- **Approval gate**: review agent plans before execution (auto-approve for QUICK)
- **Real-time OFFICE FEED**: shows agent activity, tool calls, and reports as missions execute
- **Auto work notes**: mission results are automatically saved as work notes on completion
- **Mission console**: SSE-streamed execution log with agent conversations

### Intelligence
- **148 tools**: 19 native + 129 MCP (11 servers)
- Smart Router: auto-classifies into 4 execution paths (chat/task/background/project)
- DynamicToolExecutor with continuation support
- ToolGraph v2: BFS tool discovery (~26 microseconds per query, zero API calls)
- Artifact Store: Redis-based inter-phase data sharing
- Review Loop: automatic code review + fix cycles

### Autonomous Execution
- AutonomousRunner v1.8.0: up to 8 hours, 50 steps background execution
- **Iteration Gate**: triple-check safety (completion signal + context budget + iteration count)
- **Completion Signals**: agents declare `[TASK_COMPLETE]`, `[BLOCKED]`, `[ERROR]`, `[CONTINUE]`
- Redis checkpoints for crash recovery
- Task chaining with `depends_on` for building pipelines
- Telegram progress reports every 15 minutes

### AAI Infrastructure (Agent-Agent Interaction)
- **Shared Whiteboard**: Redis-backed shared canvas — guidelines (always-active rules) + memos (auto-discovered by agents)
- **Trigger Engine**: 5 trigger types (cron / event / idle / interaction / threshold) with Redis persistence
- **Autonomy Dial**: 4-level per-agent autonomy (Watch → Plan → Confirm → Auto) — Smashing Magazine "Shared Autonomy Controls" pattern
- **Inbox**: Redis-based async message queue between agents (deliver/read/mark_read)
- **Relevance Gate**: keyword + LLM 2-stage filter — only relevant agents respond to broadcasts
- **Goal Hierarchy**: company → team → agent → task goals with mission linking
- **Heartbeat Protocol**: periodic agent wake-up with checklist-based autonomous execution
- **Atomic Checkout**: Redis SETNX mission locking (409 Conflict pattern)
- **Budget Enforcement**: per-agent monthly API cost tracking (ok → warning → hard_stop)
- **Routine Engine**: cron-based recurring mission generation with concurrency policies
- **WaveNoter Sync**: JX_SECRETARY auto-syncs voice memos from WaveNote → Whiteboard every 10 min
- **Config Revision**: agent configuration versioning with rollback support
- **SOUL.md**: file-based agent personas (SOUL.md + RULES.md) with runtime editing
- **Structured Output**: Pydantic schema injection + 2-stage LLM retry for reliable JSON parsing

### Memory System
- 3-tier: Redis (short-term) + Qdrant (long-term vectors) + SQLite (metadata)
- **LLM Memory Gate**: haiku decides if memory search is needed before querying Qdrant
- Automatic reflection: generates high-level insights when importance threshold is reached
- Semantic search across long-term memory
- Time-decay pruning with configurable half-life

### Frontend
- **10 tabs**: Office, Corporation, Projects, Memory, Logs, Tools, Notes, Settings, Autopilot, Workflow
- **Autopilot Tab**: Control Panel (autonomy dial + heartbeat), Triggers, Comms (inter-agent inbox), Budget dashboard, Routine manager
- **Workflow Tab**: React Flow-based agent execution graph visualization (BFS layout, MiniMap, Controls)
- **Whiteboard Panel**: overlay UI with guidelines/memos tabs, CRUD, status badges, tag filtering
- **Memory File Tree**: hierarchical category → result nodes with importance dots, expand/collapse
- **Schema-based Settings**: dynamic config form from `/status/config/schema` API
- Single source of truth: `TEAM_CONFIG` in `personas.ts` drives all team-related UI
- Real-time SSE streaming with smooth typing animation
- Team channels (Matrix/Synapse integration)
- Docker log panel (VSCode-style resizable)

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | FastAPI + LangGraph, Python 3.11+ |
| **Frontend** | Next.js 14 + Zustand + TailwindCSS |
| **Memory** | Redis (short-term) + Qdrant (long-term vectors) + SQLite (metadata) |
| **AI** | Anthropic Claude API (Sonnet 4.6 + Haiku 4.5) |
| **Tools** | 19 native + 11 MCP servers (129 tools) + runtime MCP loader |
| **Channels** | Web UI, Telegram bot, CLI, background daemon |
| **Infra** | Docker Compose, PM2, volume-mounted source |

---

## Organization & HR System

JINXUS runs as a virtual Korean IT company with 28 default employees across 6 teams. Each agent has a unique persona defined in `personas.py` — name, MBTI, personality, speech style, work habits, and inter-agent relationships.

**Default Teams:** Executive (4) · Development (6) · Platform (6) · Product (6) · Marketing (4) · Biz Support (2)

### Dynamic Hiring & Firing

Agents are managed through a full HR lifecycle — hire, fire, and rehire at runtime without restart.

**Hire** (`POST /hr/hire`):
- Specify specialty (coding, research, writing, etc.) and the system auto-provisions everything
- Auto-assigns: persona (name, team, channel), tool policy (inherited from parent agent type), org chart placement, playground desk, team channel membership
- Appears immediately in the Pixel Office and starts receiving tasks

**Fire** (`POST /hr/fire/{id}`):
- Soft-delete: record preserved for potential rehire, agent instance removed
- Cascade: firing a team lead automatically fires all their subordinates
- Auto-cleanup: persona unregistered, removed from playground and channels

**Rehire** (`POST /hr/rehire/{id}`):
- Reactivates a previously fired agent from the fired agents list

All personas are defined as a single source of truth in `personas.py` (backend) and synced to the frontend via `/api/agents/personas`. The frontend `TEAM_CONFIG` in `personas.ts` drives all team-related UI (colors, channels, room layouts) from one central config.

---

## Project Structure

```
backend/jinxus/
  agents/              # JINXUS_CORE + sub-agents + coding/research teams
  api/routers/         # FastAPI endpoints (chat, mission, logs, agents, etc.)
  core/                # Orchestrator, mission executor, whiteboard, trigger engine, AAI infra
  memory/              # 3-tier memory + reflection + LLM gate
  tools/               # 19 native tools + DynamicToolExecutor + MCP client
  hr/                  # Agent hiring/firing, company channels
  config/              # Settings, MCP server definitions

frontend/src/
  components/
    playground/        # Pixel Office engine (modularized)
      engine/          #   Camera, pathfinding, scheduler, social, types
      sprites/         #   Character (16x24), furniture (15 types), colors, icons
      map/             #   60x40 map data with indoor + outdoor zones
      render/          #   Emoji activity display
      poi/             #   POI state management
    tabs/              # Office, Corporation, Projects, Memory, Logs, Tools, Notes, Settings
  lib/                 # API client, SSE parser, personas (TEAM_CONFIG single source)
  store/               # Zustand global state
```

---

## Quick Start

### Prerequisites
- Docker and Docker Compose
- Anthropic API key
- Node.js 18+

### Backend

```bash
cd backend
cp .env.example .env   # Add ANTHROPIC_API_KEY
docker compose up -d   # Starts FastAPI + Redis + Qdrant
```

### Frontend

```bash
cd frontend
bash dev.sh   # Auto-installs deps, builds, starts via pm2
```

### Access

| Service | URL |
|---------|-----|
| Web UI | `http://localhost:5000` |
| Backend API | `http://localhost:19000` |
| Swagger Docs | `http://localhost:19000/docs` |

---

## Version History

| Version | Date | Highlights |
|---------|------|------------|
| **v4.1.1** | 2026-04-04 | AgentCallbackMixin (tool usage fix for all agents), mission log sync fix, sequential event ordering fix, internal codename → display name conversion |
| **v4.1.0** | 2026-04-03 | Shared Whiteboard (AAI Phase 2), Trigger Engine (5 types), Autopilot Tab (5 sub-panels), Workflow Tab (React Flow), JX_SECRETARY WaveNoter sync, Autonomy Dial, schema-based Settings, memory file tree, 12 Geny UI improvements |
| **v4.0.0** | 2026-04-01 | AAI infrastructure (Inbox, Goals, Heartbeat, Budget, Routine, Mission Lock, Config Revision), SOUL.md agent personas, Iteration Gate triple-check, LLM memory gate, Structured Output retry, Toast gating, 31 new API endpoints |
| v3.1.1 | 2026-03-26 | SSE Geny pattern, session management, agent rename, Telegram integration |
| **v3.0.0** | 2026-03-24 | Pixel Office overhaul (60x40 map, 16x24 chibi sprites, camera system, outdoor areas), org restructure (realistic Korean IT company), mission real-time feed, global mute, tab rename (English), modular architecture (15 modules) |
| v2.9.0 | 2026-03-22 | Pixel Office Playground, UI overhaul, SSE agent streaming |
| v2.6.0 | 2026-03-19 | 5 new dev team agents (27 total), persona system |
| v2.5.0 | 2026-03-19 | Next.js architecture fixes, bundle optimization |
| v2.3.0 | 2026-03-16 | Smart Router, Artifact Store, Review Loop |
| v1.7.0 | 2026-03-12 | Background tasks: Redis checkpoints, pause/resume |
| v1.5.0 | 2026-03-09 | Docker multi-stage build, Tool Policy API |

---

## License

Private project. Not for redistribution.

---

<div align="center">

**Built by [jinsoo96](https://github.com/jinsoo96)**

Special thanks to [CocoRoF](https://github.com/CocoRoF) & [SonAIengine](https://github.com/SonAIengine)

</div>
