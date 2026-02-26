"""JINXUS FastAPI 서버"""
import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import get_settings
from core import get_orchestrator
from api.routers import (
    chat_router,
    task_router,
    feedback_router,
    agents_router,
    memory_router,
    status_router,
    improve_router,
    logs_router,
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

    # 텔레그램 봇 시작 (토큰이 있으면)
    telegram_task = None
    if settings.telegram_bot_token:
        try:
            from channels.telegram_bot import start_telegram_bot
            telegram_task = asyncio.create_task(start_telegram_bot())
            print(f"Telegram bot started: @JINXUS_bot")
        except Exception as e:
            logger.warning(f"Telegram bot failed to start: {e}")

    yield

    # 종료 시
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
