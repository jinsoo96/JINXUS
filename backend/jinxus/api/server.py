"""JINXUS FastAPI 서버"""
import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from jinxus.config import get_settings
from jinxus.core import get_orchestrator
from jinxus.api.routers import (
    chat_router,
    task_router,
    feedback_router,
    agents_router,
    memory_router,
    status_router,
    improve_router,
    logs_router,
    hr_router,
    plugins_router,
    dev_notes_router,
    projects_router,
    processes_router,
    docker_logs_router,
    channel_router,
    matrix_router,
    mission_router,
    command_router,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """서버 시작/종료 시 실행"""
    settings = get_settings()

    # 시작 시
    orchestrator = get_orchestrator()
    await orchestrator.initialize()
    print("JINXUS initialized successfully")

    # 백그라운드 워커 시작
    from jinxus.core.background_worker import start_background_worker
    await start_background_worker()
    print("Background worker started")

    # 텔레그램 봇 시작 (토큰이 있으면)
    telegram_task = None
    telegram_send_func = None
    if settings.telegram_bot_token:
        try:
            from jinxus.channels.telegram_bot import start_telegram_bot, get_telegram_send_func
            telegram_task = asyncio.create_task(start_telegram_bot())
            telegram_send_func = get_telegram_send_func()
            print(f"Telegram bot started: @JINXUS_bot")

            # Task API에 텔레그램 알림 연결
            from jinxus.api.routers.task import set_telegram_notify
            set_telegram_notify(telegram_send_func)
            print("Task API: Telegram notifications connected")
        except Exception as e:
            logger.warning(f"Telegram bot failed to start: {e}")

    # 프롬프트 버전 동기화
    try:
        from jinxus.tools import sync_all_prompts
        sync_result = await sync_all_prompts()
        print(f"Prompt versions synced: {sync_result.get('count', 0)} agents")
    except Exception as e:
        logger.error(f"Failed to sync prompts: {e}")

    # 중단된 백그라운드 작업 감지 및 보고
    try:
        from jinxus.memory.meta_store import get_meta_store
        meta = get_meta_store()
        interrupted = await meta.get_interrupted_tasks()
        if interrupted:
            msg = f"[서버 재시작] 중단된 작업 {len(interrupted)}개 감지:\n"
            for t in interrupted:
                mode = "자율" if t.get("autonomous") else "단일"
                msg += f"  - [{mode}] {t['description'][:60]}\n"
            logger.warning(msg)
            if telegram_send_func:
                try:
                    await telegram_send_func(msg)
                except Exception as e:
                    logger.warning(f"[server] 텔레그램 중단 작업 알림 전송 실패: {e}")
            print(f"Interrupted tasks reported: {len(interrupted)}")
        # 오래된 작업 정리
        await meta.cleanup_old_background_tasks(days=7)
    except Exception as e:
        logger.debug(f"Interrupted tasks check failed: {e}")

    # 고아 미션 정리 (서버 재시작 시 in_progress 상태로 남은 미션 failed 처리)
    try:
        from jinxus.core.mission_executor import get_mission_executor
        executor = get_mission_executor()
        await executor.cleanup_orphan_missions()
        print("Orphan missions cleaned up (v3)")
    except Exception as e:
        logger.warning(f"Orphan mission cleanup failed: {e}")

    # v4 CLI 엔진 초기화
    try:
        from jinxus.cli_engine.session_manager import get_agent_session_manager
        from jinxus.tools.tool_loader import load_global_mcp_servers

        session_mgr = get_agent_session_manager()
        session_mgr.set_defaults(
            working_dir=settings.workspace_root if hasattr(settings, 'workspace_root') else None,
            model=settings.claude_model,
            mcp_config=None,  # MCP는 에이전트 생성 시 개별 빌드
        )
        session_mgr.start_idle_monitor()
        print("CLI Engine: AgentSessionManager initialized")

        # v4 MissionExecutor 고아 정리
        from jinxus.core.mission_executor_v4 import get_mission_executor_v4
        executor_v4 = get_mission_executor_v4()
        await executor_v4.cleanup_orphan_missions()
        print("CLI Engine: MissionExecutor v4 ready")
    except Exception as e:
        logger.warning(f"CLI Engine init failed (v4 features disabled): {e}")

    # 스케줄러 초기화 및 복구
    try:
        from jinxus.tools import TOOL_REGISTRY

        scheduler = TOOL_REGISTRY.get("scheduler")
        if scheduler:
            # 스케줄된 작업 실행 콜백 (JINXUS_CORE로 처리)
            async def task_callback(task_prompt: str) -> str:
                from jinxus.core import get_orchestrator
                orchestrator = get_orchestrator()
                result = await orchestrator.process(task_prompt, session_id="scheduled_task")
                return result.get("response", "완료")

            scheduler.initialize(
                task_callback=task_callback,
                notification_callback=telegram_send_func,
            )
            restored = await scheduler.restore_from_db()
            print(f"Scheduler initialized, restored {restored} tasks")
    except Exception as e:
        logger.error(f"Failed to initialize scheduler: {e}")

    # 프로젝트 매니저 복원
    try:
        from jinxus.core.project_manager import get_project_manager
        pm = get_project_manager()
        await pm.restore_projects()
        print("ProjectManager: projects restored")
    except Exception as e:
        logger.debug(f"ProjectManager restore failed: {e}")

    # Matrix 에이전트 셋업 (Synapse가 실행 중이면 가상 계정 + 룸 초기화)
    try:
        from jinxus.channels.matrix_channel import get_matrix_as
        matrix_as = get_matrix_as()
        asyncio.create_task(matrix_as.setup_all_agents())
        print("Matrix agent setup scheduled")
    except Exception as e:
        logger.warning(f"Matrix setup failed: {e}")

    # 상태 추적기 Redis 초기화
    try:
        from jinxus.agents.state_tracker import get_state_tracker
        tracker = get_state_tracker()
        await tracker.init_redis()
    except Exception as e:
        logger.debug(f"StateTracker Redis init failed (in-memory mode): {e}")

    # 메트릭 복원 + 주기적 스냅샷
    metrics_task = None
    try:
        from jinxus.core.metrics import get_metrics
        import redis.asyncio as aioredis
        metrics_redis = aioredis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            password=settings.redis_password if settings.redis_password else None,
            decode_responses=True,
        )
        metrics = get_metrics()
        await metrics.restore_snapshot(metrics_redis)

        async def _periodic_metrics_save():
            while True:
                await asyncio.sleep(300)  # 5분
                try:
                    await metrics.save_snapshot(metrics_redis)
                except Exception as e:
                    logger.warning(f"[server] 메트릭 주기적 스냅샷 저장 실패: {e}")

        metrics_task = asyncio.create_task(_periodic_metrics_save())
        print("Metrics snapshot: restore done, auto-save every 5m")
    except Exception as e:
        logger.debug(f"Metrics snapshot init failed: {e}")

    # 메모리 최적화 (시작 시 1회 + 24시간 주기)
    memory_cleanup_task = None
    try:
        from jinxus.memory.long_term import get_long_term_memory

        async def _run_memory_optimization():
            """시간 감쇠 정리 + 중복 제거 실행"""
            try:
                ltm = get_long_term_memory()
                results = await asyncio.to_thread(ltm.optimize_all_collections)
                total_pruned = sum(r["pruned"] for r in results.values())
                total_deduped = sum(r["deduped"] for r in results.values())
                if total_pruned > 0 or total_deduped > 0:
                    logger.info(
                        f"[MemoryOptim] 최적화: {total_pruned}개 정리, {total_deduped}개 중복 제거"
                    )
                return total_pruned, total_deduped
            except Exception as e:
                logger.warning(f"[MemoryOptim] 최적화 실패: {e}")
                return 0, 0

        # 시작 시 1회 실행 (백그라운드)
        asyncio.create_task(_run_memory_optimization())
        print("Memory optimization: startup run scheduled")

        async def _periodic_memory_optimize():
            while True:
                await asyncio.sleep(24 * 3600)  # 24시간
                await _run_memory_optimization()

        memory_cleanup_task = asyncio.create_task(_periodic_memory_optimize())
        print("Memory optimization: periodic run every 24h")
    except Exception as e:
        logger.debug(f"Memory optimization schedule failed: {e}")

    yield

    # 종료 시
    # 관리 프로세스 정리
    try:
        from jinxus.core.subprocess_manager import get_subprocess_manager
        await get_subprocess_manager().stop_all()
    except Exception as e:
        logger.debug(f"[server] SubprocessManager 종료 중 오류: {e}")

    from jinxus.core.background_worker import stop_background_worker
    await stop_background_worker()

    # JinxMemory 쓰기 풀 종료
    try:
        from jinxus.memory import get_jinx_memory
        get_jinx_memory().close()
    except Exception as e:
        logger.debug(f"[server] JinxMemory 종료 중 오류: {e}")

    # StateTracker Redis 종료
    try:
        from jinxus.agents.state_tracker import get_state_tracker
        await get_state_tracker().close()
    except Exception as e:
        logger.debug(f"[server] StateTracker 종료 중 오류: {e}")

    # ArtifactStore Redis 종료
    try:
        from jinxus.core.artifact_store import get_artifact_store
        await get_artifact_store().close()
    except Exception as e:
        logger.debug(f"[server] ArtifactStore 종료 중 오류: {e}")

    # ShortTermMemory Redis 종료
    try:
        from jinxus.memory.short_term import get_short_term_memory
        await get_short_term_memory().disconnect()
    except Exception as e:
        logger.debug(f"[server] ShortTermMemory 종료 중 오류: {e}")

    # CompanyChannel Redis 종료
    try:
        from jinxus.hr.channel import get_company_channel
        await get_company_channel().close()
    except Exception as e:
        logger.debug(f"[server] CompanyChannel 종료 중 오류: {e}")

    # MatrixAS 세션 종료
    try:
        from jinxus.channels.matrix_channel import get_matrix_as
        await get_matrix_as().close()
    except Exception as e:
        logger.debug(f"[server] MatrixAS 종료 중 오류: {e}")

    # ApprovalGate Redis 종료
    try:
        from jinxus.core.approval_gate import get_approval_gate
        await get_approval_gate().close()
    except Exception as e:
        logger.debug(f"[server] ApprovalGate 종료 중 오류: {e}")

    # MissionStore Redis 종료
    try:
        from jinxus.core.mission import get_mission_store
        await get_mission_store().close()
    except Exception as e:
        logger.debug(f"[server] MissionStore 종료 중 오류: {e}")

    # 스케줄러 종료
    try:
        from jinxus.tools import TOOL_REGISTRY
        scheduler = TOOL_REGISTRY.get("scheduler")
        if scheduler:
            scheduler.shutdown()
    except Exception as e:
        logger.error(f"Failed to shutdown scheduler: {e}")

    # 메트릭 최종 스냅샷 저장
    if metrics_task:
        metrics_task.cancel()
        try:
            await metrics.save_snapshot(metrics_redis)
            await metrics_redis.close()
        except Exception as e:
            logger.debug(f"[server] 메트릭 종료 정리 중 오류: {e}")

    # CLI Engine 세션 정리
    try:
        from jinxus.cli_engine.session_manager import get_agent_session_manager
        mgr = get_agent_session_manager()
        await mgr.stop_idle_monitor()
        for session in mgr.list_sessions():
            await session.cleanup()
        print("CLI Engine: all sessions cleaned up")
    except Exception as e:
        logger.debug(f"[server] CLI Engine 종료 중 오류: {e}")

    if memory_cleanup_task:
        memory_cleanup_task.cancel()
    if telegram_task:
        telegram_task.cancel()
    print("JINXUS shutting down")


def create_app() -> FastAPI:
    """FastAPI 앱 팩토리"""
    settings = get_settings()

    app = FastAPI(
        title="JINXUS",
        description="Just Intelligent Nexus, eXecutes Under Supremacy - 진수의 AI 비서 시스템",
        version=settings.jinxus_version,
        lifespan=lifespan,
        debug=settings.jinxus_debug,
    )

    # CORS 설정
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 라우터 등록
    app.include_router(chat_router)
    app.include_router(task_router)
    app.include_router(feedback_router)
    app.include_router(agents_router)
    app.include_router(memory_router)
    app.include_router(status_router)
    app.include_router(improve_router)
    app.include_router(logs_router)
    app.include_router(hr_router)
    app.include_router(plugins_router)
    app.include_router(dev_notes_router)
    app.include_router(projects_router)
    app.include_router(processes_router)
    app.include_router(docker_logs_router)
    app.include_router(channel_router)
    app.include_router(matrix_router)
    app.include_router(mission_router)
    app.include_router(command_router)

    @app.get("/")
    async def root():
        """루트 엔드포인트"""
        return {
            "name": "JINXUS",
            "tagline": "명령만 해. 나머지는 내가 다 한다.",
            "version": settings.jinxus_version,
            "status": "running",
        }

    return app


# 앱 인스턴스
app = create_app()
