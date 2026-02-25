"""텔레그램 봇 — JINXUS_CORE와 연결

폰에서도 JINXUS를 사용할 수 있게 해주는 텔레그램 봇.

사용법:
    1. .env에 TELEGRAM_BOT_TOKEN, TELEGRAM_AUTHORIZED_USER_ID 설정
    2. main.py에서 start_telegram_bot() 호출

특수 명령:
    /status  - 시스템 상태 확인
    /agents  - 에이전트 목록
    /memory <검색어> - 장기기억 검색
    /cancel  - 현재 작업 취소
"""
import asyncio
import logging
from typing import Optional

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from config import get_settings
from core.orchestrator import get_orchestrator

logger = logging.getLogger(__name__)


class TelegramBot:
    """JINXUS 텔레그램 봇"""

    def __init__(self):
        settings = get_settings()
        self._token = settings.telegram_bot_token
        self._authorized_user_id = settings.telegram_authorized_user_id
        self._app: Optional[Application] = None
        self._orchestrator = None

    def _is_authorized(self, user_id: int) -> bool:
        """사용자 인증 확인"""
        # authorized_user_id가 0이면 모든 사용자 허용 (개발용)
        if self._authorized_user_id == 0:
            return True
        return user_id == self._authorized_user_id

    async def _handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """일반 메시지 처리 → JINXUS_CORE 실행"""
        if not update.effective_user or not update.message:
            return

        user_id = update.effective_user.id
        if not self._is_authorized(user_id):
            await update.message.reply_text("인증되지 않은 사용자입니다.")
            return

        user_input = update.message.text
        chat_id = update.effective_chat.id

        # 처리 중 메시지
        thinking_msg = await context.bot.send_message(
            chat_id, "처리 중입니다, 주인님..."
        )

        try:
            if not self._orchestrator:
                self._orchestrator = get_orchestrator()
                await self._orchestrator.initialize()

            # JINXUS_CORE 실행
            result = await self._orchestrator.run_task(
                user_input=user_input,
                session_id=f"telegram_{chat_id}",
            )

            response = result["response"]

            # 처리 중 메시지 삭제
            await thinking_msg.delete()

            # 텔레그램 4096자 제한 처리
            for i in range(0, len(response), 4000):
                chunk = response[i:i+4000]
                await context.bot.send_message(
                    chat_id,
                    chunk,
                    parse_mode="Markdown",
                )

        except Exception as e:
            logger.error(f"Telegram message handling error: {e}")
            await thinking_msg.edit_text(f"오류가 발생했습니다: {str(e)[:200]}")

    async def _cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """/start 명령"""
        if not update.message:
            return
        await update.message.reply_text(
            "안녕하세요, 주인님! JINXUS입니다.\n"
            "무엇이든 명령해주세요.\n\n"
            "사용 가능한 명령:\n"
            "/status - 시스템 상태\n"
            "/agents - 에이전트 목록\n"
            "/memory <검색어> - 기억 검색"
        )

    async def _cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """/status 명령 - 시스템 상태"""
        if not update.message:
            return

        if not self._is_authorized(update.effective_user.id):
            return

        try:
            if not self._orchestrator:
                self._orchestrator = get_orchestrator()
                await self._orchestrator.initialize()

            status = await self._orchestrator.get_system_status()

            status_text = (
                f"**JINXUS 시스템 상태**\n\n"
                f"상태: {status.get('status', 'unknown')}\n"
                f"가동 시간: {status.get('uptime_seconds', 0)}초\n"
                f"Redis: {'연결됨' if status.get('redis_connected') else '연결 안됨'}\n"
                f"Qdrant: {'연결됨' if status.get('qdrant_connected') else '연결 안됨'}\n"
                f"처리된 작업: {status.get('total_tasks_processed', 0)}개\n"
                f"활성 에이전트: {', '.join(status.get('active_agents', []))}"
            )

            await update.message.reply_text(status_text, parse_mode="Markdown")

        except Exception as e:
            await update.message.reply_text(f"상태 조회 오류: {e}")

    async def _cmd_agents(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """/agents 명령 - 에이전트 목록"""
        if not update.message:
            return

        if not self._is_authorized(update.effective_user.id):
            return

        try:
            if not self._orchestrator:
                self._orchestrator = get_orchestrator()
                await self._orchestrator.initialize()

            agents = self._orchestrator.get_agents()

            agents_text = "**등록된 에이전트**\n\n"
            for agent_name in agents:
                status = await self._orchestrator.get_agent_status(agent_name)
                agents_text += f"- {agent_name} (v{status.get('prompt_version', '1.0')})\n"

            await update.message.reply_text(agents_text, parse_mode="Markdown")

        except Exception as e:
            await update.message.reply_text(f"에이전트 조회 오류: {e}")

    async def _cmd_memory(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """/memory 명령 - 장기기억 검색"""
        if not update.message:
            return

        if not self._is_authorized(update.effective_user.id):
            return

        # 검색어 추출
        query = " ".join(context.args) if context.args else ""
        if not query:
            await update.message.reply_text("검색어를 입력해주세요.\n예: /memory 피보나치")
            return

        try:
            if not self._orchestrator:
                self._orchestrator = get_orchestrator()
                await self._orchestrator.initialize()

            # 메모리 검색
            from memory import get_jinx_memory
            memory = get_jinx_memory()
            results = memory.search_all_memories(query, limit=5)

            if not results:
                await update.message.reply_text("검색 결과가 없습니다.")
                return

            memory_text = f"**'{query}' 검색 결과**\n\n"
            for r in results:
                summary = r.get("summary", "")[:100]
                agent = r.get("agent_name", "UNKNOWN")
                memory_text += f"- [{agent}] {summary}...\n\n"

            await update.message.reply_text(memory_text, parse_mode="Markdown")

        except Exception as e:
            await update.message.reply_text(f"메모리 검색 오류: {e}")

    def build_app(self) -> Application:
        """텔레그램 봇 앱 빌드"""
        if not self._token:
            raise ValueError("TELEGRAM_BOT_TOKEN is not set")

        self._app = Application.builder().token(self._token).build()

        # 핸들러 등록
        self._app.add_handler(CommandHandler("start", self._cmd_start))
        self._app.add_handler(CommandHandler("status", self._cmd_status))
        self._app.add_handler(CommandHandler("agents", self._cmd_agents))
        self._app.add_handler(CommandHandler("memory", self._cmd_memory))
        self._app.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_message)
        )

        return self._app

    async def start(self):
        """봇 시작 (polling 모드)"""
        app = self.build_app()
        logger.info("Starting Telegram bot...")
        await app.initialize()
        await app.start()
        await app.updater.start_polling()

    async def stop(self):
        """봇 종료"""
        if self._app:
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()


# 전역 봇 인스턴스
_telegram_bot: Optional[TelegramBot] = None


def get_telegram_bot() -> TelegramBot:
    """텔레그램 봇 싱글톤"""
    global _telegram_bot
    if _telegram_bot is None:
        _telegram_bot = TelegramBot()
    return _telegram_bot


async def start_telegram_bot():
    """텔레그램 봇 시작 (main.py에서 호출)"""
    settings = get_settings()
    if not settings.telegram_bot_token:
        logger.warning("TELEGRAM_BOT_TOKEN not set, skipping Telegram bot")
        return

    bot = get_telegram_bot()
    await bot.start()


async def send_notification(message: str):
    """텔레그램으로 알림 전송 (스케줄 작업 완료 등)"""
    settings = get_settings()
    if not settings.telegram_bot_token or not settings.telegram_authorized_user_id:
        return

    try:
        from telegram import Bot
        bot = Bot(token=settings.telegram_bot_token)
        await bot.send_message(
            chat_id=settings.telegram_authorized_user_id,
            text=message,
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error(f"Failed to send Telegram notification: {e}")
