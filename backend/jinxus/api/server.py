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

    # 스케줄러 초기화 및 복구
    try:
        from jinxus.tools import TOOL_REGISTRY

        scheduler = TOOL_REGISTRY.get("scheduler")
        if scheduler:
            # 스케줄된 작업 실행 콜백 (JINXUS_CORE로 처리)
            async def task_callback(task_prompt: str) -> str:
                from jinxus.agents import get_jinxus_core
                jinxus_core = get_jinxus_core()
                result = await jinxus_core.run(task_prompt, session_id="scheduled_task")
                return result.get("response", "완료")

            scheduler.initialize(
                task_callback=task_callback,
                notification_callback=telegram_send_func,
            )
            restored = await scheduler.restore_from_db()
            print(f"Scheduler initialized, restored {restored} tasks")
    except Exception as e:
        logger.error(f"Failed to initialize scheduler: {e}")

    yield

    # 종료 시
    from jinxus.core.background_worker import stop_background_worker
    await stop_background_worker()

    # 스케줄러 종료
    try:
        from jinxus.tools import TOOL_REGISTRY
        scheduler = TOOL_REGISTRY.get("scheduler")
        if scheduler:
            scheduler.shutdown()
    except Exception as e:
        logger.error(f"Failed to shutdown scheduler: {e}")

    if telegram_task:
        telegram_task.cancel()
    print("JINXUS shutting down")


def create_app() -> FastAPI:
    """FastAPI 앱 팩토리"""
    settings = get_settings()

    app = FastAPI(
        title="JINXUS",
        description="Just Intelligent Nexus, eXecutes Under Supremacy - 진수의 AI 비서 시스템",
        version="1.0.0",
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

    @app.get("/")
    async def root():
        """루트 엔드포인트"""
        return {
            "name": "JINXUS",
            "tagline": "명령만 해. 나머지는 내가 다 한다.",
            "version": "1.0.0",
            "status": "running",
        }

    return app


# 앱 인스턴스
app = create_app()
