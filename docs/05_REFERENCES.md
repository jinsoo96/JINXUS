# 참조 문서 및 링크

## 설계 시 직접 읽고 참고한 소스

| 소스 | 링크 | 참고한 내용 |
|---|---|---|
| **claude_company** | [github.com/CocoRoF/claude_company](https://github.com/CocoRoF/claude_company) | Claude Code CLI를 subprocess로 감싸는 방식, MCP 자동 로딩 패턴, `CLAUDE_DANGEROUSLY_SKIP_PERMISSIONS` 환경변수 활용법 → `code_executor` 툴 설계에 반영 |
| **Geny** | [github.com/CocoRoF/Geny](https://github.com/CocoRoF/Geny) | FastAPI + LangGraph 백엔드 구조, 단기/장기 메모리 분리 레이어 개념, context_guard / model_fallback 노드 아이디어, 역할 기반 프롬프트 분리 방식 → JinxBrain 그래프 구조와 JinxMemory 3계층 설계에 반영. **2차 심층 분석 (2026-03-08)**: 난이도 기반 그래프 분기, Session Freshness Policy, Resilience Node 패턴, Tool Policy Engine, LangGraph Checkpointer 5개 패턴 식별 → [07_GENY_ANALYSIS.md](07_GENY_ANALYSIS.md) 참조 |
| **XGEN / SON BLOG** | [infoedu.co.kr](https://infoedu.co.kr) | K3s + Jenkins + ArgoCD CI/CD 파이프라인 구성, Istio 서비스 메시 + Observability 스택, GPU 모델 서빙 아키텍처, Qdrant 기반 임베딩 최적화 → Phase 5 배포 인프라 및 향후 파인튜닝 파이프라인 설계 방향에 반영 |
| **XGEN_Working_dir** | [github.com/jinsoo96/XGEN_Working_dir](https://github.com/jinsoo96/XGEN_Working_dir) | Private 레포라 직접 접근 불가. infoedu.co.kr 블로그 기반으로 XGEN 플랫폼 구조 간접 파악. |

## 기술 공식 문서

| 기술 | 공식 문서 |
|---|---|
| LangGraph | [langchain-ai.github.io/langgraph](https://langchain-ai.github.io/langgraph/) |
| Anthropic Claude API | [docs.anthropic.com](https://docs.anthropic.com) |
| Claude Code CLI | [docs.anthropic.com/claude-code](https://docs.anthropic.com/en/docs/claude-code) |
| Qdrant | [qdrant.tech/documentation](https://qdrant.tech/documentation/) |
| FastAPI | [fastapi.tiangolo.com](https://fastapi.tiangolo.com) |
| APScheduler | [apscheduler.readthedocs.io](https://apscheduler.readthedocs.io) |
| Tavily API | [docs.tavily.com](https://docs.tavily.com) |

## 추가 레퍼런스

| 주제 | 링크 | 이유 |
|---|---|---|
| LangGraph 메모리 패턴 | [langchain-ai.github.io/langgraph/concepts/memory](https://langchain-ai.github.io/langgraph/concepts/memory/) | JinxMemory 구현 시 공식 패턴 참고 |
| Qdrant 필터링 + 페이로드 | [qdrant.tech/documentation/concepts/filtering](https://qdrant.tech/documentation/concepts/filtering/) | importance_score 기반 pruning 쿼리 작성 시 |
| Claude Code SDK | [github.com/anthropics/claude-code](https://github.com/anthropics/claude-code) | code_executor 툴에서 CLI 대신 SDK 쓸 경우 |
| MCP 프로토콜 명세 | [modelcontextprotocol.io](https://modelcontextprotocol.io) | JinxTools를 MCP 서버로 확장할 때 |
