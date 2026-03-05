"""텔레그램 봇 — JINXUS_CORE와 연결

폰에서도 JINXUS를 사용할 수 있게 해주는 텔레그램 봇.

사용법:
    1. .env에 TELEGRAM_BOT_TOKEN, TELEGRAM_AUTHORIZED_USER_ID 설정
    2. main.py에서 start_telegram_bot() 호출

특수 명령:
    /status   - 시스템 상태 확인
    /agents   - 에이전트 목록
    /memory   - 장기기억 검색
    /improve  - 자가 강화 수동 트리거
    /schedule - 예약 작업 관리
    /bg       - 백그라운드 작업 (긴 작업용)
    /tasks    - 백그라운드 작업 목록
    /cancel   - 작업 취소
"""
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

from jinxus.config import get_settings
from jinxus.core.orchestrator import get_orchestrator

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

            # 텔레그램 4096자 제한 처리 (plain text로 전송 - 마크다운 파싱 에러 방지)
            for i in range(0, len(response), 4000):
                chunk = response[i:i+4000]
                await context.bot.send_message(chat_id, chunk)

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
            "/memory <검색어> - 기억 검색\n"
            "/improve [에이전트] - 자가 강화\n"
            "/schedule - 예약 작업 관리\n"
            "/bg <작업> - 백그라운드 실행 (긴 작업)\n"
            "/tasks - 백그라운드 작업 목록\n"
            "/cancel <ID> - 작업 취소"
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

            agents_list = ', '.join(status.get('active_agents', [])) or '없음'
            status_text = (
                f"[JINXUS 시스템 상태]\n\n"
                f"상태: {status.get('status', 'unknown')}\n"
                f"가동 시간: {status.get('uptime_seconds', 0)}초\n"
                f"Redis: {'연결됨' if status.get('redis_connected') else '연결 안됨'}\n"
                f"Qdrant: {'연결됨' if status.get('qdrant_connected') else '연결 안됨'}\n"
                f"처리된 작업: {status.get('total_tasks_processed', 0)}개\n"
                f"활성 에이전트: {agents_list}"
            )

            await update.message.reply_text(status_text)

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

            agents_text = "[등록된 에이전트]\n\n"
            for agent_name in agents:
                status = await self._orchestrator.get_agent_status(agent_name)
                agents_text += f"• {agent_name} (v{status.get('prompt_version', '1.0')})\n"

            await update.message.reply_text(agents_text)

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
            from jinxus.memory import get_jinx_memory
            memory = get_jinx_memory()
            results = memory.search_all_memories(query, limit=5)

            if not results:
                await update.message.reply_text("검색 결과가 없습니다.")
                return

            memory_text = f"['{query}' 검색 결과]\n\n"
            for r in results:
                summary = r.get("summary", "")[:100]
                agent = r.get("agent_name", "UNKNOWN")
                memory_text += f"• [{agent}] {summary}...\n\n"

            await update.message.reply_text(memory_text)

        except Exception as e:
            await update.message.reply_text(f"메모리 검색 오류: {e}")

    async def _cmd_improve(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """/improve 명령 - 자가 강화 수동 트리거"""
        if not update.message:
            return

        if not self._is_authorized(update.effective_user.id):
            return

        # 에이전트 지정 (선택)
        agent_name = context.args[0] if context.args else None

        await update.message.reply_text("자가 강화 프로세스 시작 중...")

        try:
            if not self._orchestrator:
                self._orchestrator = get_orchestrator()
                await self._orchestrator.initialize()

            # JinxLoop 자가 강화 실행
            from jinxus.core.jinx_loop import get_jinx_loop
            jinx_loop = get_jinx_loop()

            if agent_name:
                # 특정 에이전트만 강화
                result = await jinx_loop.improve_agent(agent_name)
                if result:
                    await update.message.reply_text(
                        f"[자가 강화 완료]\n\n"
                        f"에이전트: {agent_name}\n"
                        f"결과: {result.get('status', 'unknown')}\n"
                        f"개선 사항: {result.get('improvement', 'N/A')[:200]}"
                    )
                else:
                    await update.message.reply_text(f"{agent_name} 에이전트 강화 데이터 부족")
            else:
                # 전체 에이전트 강화
                results = await jinx_loop.run_improvement_cycle()
                if results:
                    text = "[자가 강화 완료]\n\n"
                    for agent, res in results.items():
                        status = res.get('status', 'skipped')
                        text += f"• {agent}: {status}\n"
                    await update.message.reply_text(text)
                else:
                    await update.message.reply_text("강화할 에이전트가 없습니다 (최근 작업 없음)")

        except Exception as e:
            logger.error(f"Improve command error: {e}")
            await update.message.reply_text(f"자가 강화 오류: {str(e)[:200]}")

    async def _cmd_schedule(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """/schedule 명령 - 예약 작업 관리

        사용법:
            /schedule           - 예약 작업 목록
            /schedule add <시간> <작업>  - 작업 추가 (예: /schedule add 09:00 날씨 알려줘)
            /schedule remove <ID> - 작업 삭제
        """
        if not update.message:
            return

        if not self._is_authorized(update.effective_user.id):
            return

        args = context.args if context.args else []

        try:
            from jinxus.tools import Scheduler
            scheduler = Scheduler()

            # 인자 없으면 목록 조회
            if not args:
                jobs = scheduler.list_jobs()
                if not jobs:
                    await update.message.reply_text("예약된 작업이 없습니다.")
                    return

                text = "[예약 작업 목록]\n\n"
                for job in jobs:
                    text += f"• [{job['id'][:8]}] {job.get('name', 'unnamed')}\n"
                    text += f"  다음 실행: {job.get('next_run', 'N/A')}\n\n"
                await update.message.reply_text(text)
                return

            action = args[0].lower()

            if action == "add" and len(args) >= 3:
                # /schedule add 09:00 날씨 알려줘
                time_str = args[1]
                task_desc = " ".join(args[2:])

                # cron 형식으로 변환 (HH:MM -> hour, minute)
                try:
                    hour, minute = map(int, time_str.split(":"))
                except ValueError:
                    await update.message.reply_text("시간 형식 오류. 예: 09:00")
                    return

                # 매일 해당 시간에 실행하는 작업 등록
                job_id = await scheduler.add_daily_job(
                    hour=hour,
                    minute=minute,
                    task_description=task_desc,
                    callback=self._scheduled_task_callback,
                )

                await update.message.reply_text(
                    f"[작업 예약 완료]\n\n"
                    f"ID: {job_id[:8]}\n"
                    f"시간: 매일 {time_str}\n"
                    f"작업: {task_desc}"
                )

            elif action == "remove" and len(args) >= 2:
                # /schedule remove <id>
                job_id = args[1]
                success = scheduler.remove_job(job_id)
                if success:
                    await update.message.reply_text(f"작업 {job_id[:8]} 삭제됨")
                else:
                    await update.message.reply_text(f"작업 {job_id[:8]}를 찾을 수 없음")

            else:
                await update.message.reply_text(
                    "사용법:\n"
                    "/schedule - 목록\n"
                    "/schedule add HH:MM 작업내용 - 추가\n"
                    "/schedule remove ID - 삭제"
                )

        except Exception as e:
            logger.error(f"Schedule command error: {e}")
            await update.message.reply_text(f"스케줄 오류: {str(e)[:200]}")

    async def _cmd_bg(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """/bg 명령 - 백그라운드 작업 제출

        긴 작업을 백그라운드에서 실행하고 완료 시 알림을 받음.
        예: /bg 이 프로젝트 전체 분석해줘
        """
        if not update.message:
            return

        if not self._is_authorized(update.effective_user.id):
            return

        # 작업 내용 추출
        task_description = " ".join(context.args) if context.args else ""
        if not task_description:
            await update.message.reply_text(
                "백그라운드 작업 내용을 입력해주세요.\n"
                "예: /bg 이 프로젝트 전체 분석해줘"
            )
            return

        try:
            from jinxus.core.background_worker import get_background_worker
            worker = get_background_worker()

            chat_id = update.effective_chat.id

            # 알림 콜백 생성 (이미지 지원)
            async def notify(message: str, image_paths: list[str] = None):
                await send_notification(message, image_paths=image_paths)

            # 작업 제출
            task_id = await worker.submit(
                task_description=task_description,
                session_id=f"telegram_bg_{chat_id}",
                notify_callback=notify,
            )

            await update.message.reply_text(
                f"[백그라운드 작업 등록]\n\n"
                f"ID: {task_id[:8]}\n"
                f"작업: {task_description[:100]}\n\n"
                f"완료되면 알림을 보내드립니다."
            )

        except Exception as e:
            logger.error(f"Background task submission error: {e}")
            await update.message.reply_text(f"작업 등록 오류: {str(e)[:200]}")

    async def _cmd_tasks(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """/tasks 명령 - 백그라운드 작업 목록"""
        if not update.message:
            return

        if not self._is_authorized(update.effective_user.id):
            return

        try:
            from jinxus.core.background_worker import get_background_worker
            worker = get_background_worker()

            all_tasks = worker.get_all_tasks()

            if not all_tasks:
                await update.message.reply_text("등록된 백그라운드 작업이 없습니다.")
                return

            # 최근 10개만 표시
            recent_tasks = sorted(all_tasks, key=lambda t: t.created_at, reverse=True)[:10]

            text = "[백그라운드 작업 목록]\n\n"
            for task in recent_tasks:
                status_emoji = {
                    "pending": "⏳",
                    "running": "🔄",
                    "completed": "✅",
                    "failed": "❌",
                    "cancelled": "🚫",
                }.get(task.status.value, "❓")

                text += f"{status_emoji} [{task.task_id[:8]}] {task.status.value}\n"
                text += f"   {task.description[:50]}...\n\n"

            await update.message.reply_text(text)

        except Exception as e:
            logger.error(f"Tasks list error: {e}")
            await update.message.reply_text(f"작업 목록 조회 오류: {str(e)[:200]}")

    async def _cmd_cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """/cancel 명령 - 백그라운드 작업 취소"""
        if not update.message:
            return

        if not self._is_authorized(update.effective_user.id):
            return

        # 작업 ID 추출
        task_id_prefix = context.args[0] if context.args else ""
        if not task_id_prefix:
            await update.message.reply_text(
                "취소할 작업 ID를 입력해주세요.\n"
                "예: /cancel abc12345"
            )
            return

        try:
            from jinxus.core.background_worker import get_background_worker
            worker = get_background_worker()

            # 짧은 ID로 검색
            all_tasks = worker.get_all_tasks()
            matched_task = None
            for task in all_tasks:
                if task.task_id.startswith(task_id_prefix):
                    matched_task = task
                    break

            if not matched_task:
                await update.message.reply_text(f"작업 {task_id_prefix}를 찾을 수 없습니다.")
                return

            success = await worker.cancel_task(matched_task.task_id)
            if success:
                await update.message.reply_text(f"작업 {task_id_prefix} 취소됨")
            else:
                await update.message.reply_text(f"작업 {task_id_prefix}는 이미 완료되었거나 취소할 수 없습니다.")

        except Exception as e:
            logger.error(f"Task cancel error: {e}")
            await update.message.reply_text(f"작업 취소 오류: {str(e)[:200]}")

    async def _scheduled_task_callback(self, task_description: str):
        """예약 작업 실행 콜백"""
        try:
            if not self._orchestrator:
                self._orchestrator = get_orchestrator()
                await self._orchestrator.initialize()

            # 작업 실행
            result = await self._orchestrator.run_task(
                user_input=task_description,
                session_id="scheduled_task",
            )

            # 결과를 텔레그램으로 알림
            response = result.get("response", "완료")[:1000]
            await send_notification(f"[예약 작업 완료]\n\n작업: {task_description}\n\n결과: {response}")

        except Exception as e:
            logger.error(f"Scheduled task error: {e}")
            await send_notification(f"[예약 작업 오류]\n\n작업: {task_description}\n오류: {str(e)[:200]}")

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
        self._app.add_handler(CommandHandler("improve", self._cmd_improve))
        self._app.add_handler(CommandHandler("schedule", self._cmd_schedule))
        self._app.add_handler(CommandHandler("bg", self._cmd_bg))
        self._app.add_handler(CommandHandler("tasks", self._cmd_tasks))
        self._app.add_handler(CommandHandler("cancel", self._cmd_cancel))
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


def get_telegram_send_func():
    """텔레그램 알림 전송 함수 반환 (스케줄러용)

    Returns:
        async def(message: str) -> None
    """
    async def send_func(message: str) -> None:
        await send_notification(message)
    return send_func


async def send_notification(message: str, image_paths: list[str] = None):
    """텔레그램으로 알림 전송 (텍스트 + 이미지)

    Args:
        message: 전송할 메시지
        image_paths: 이미지 파일 경로 리스트 (선택)
    """
    settings = get_settings()
    if not settings.telegram_bot_token or not settings.telegram_authorized_user_id:
        return

    try:
        from telegram import Bot
        bot = Bot(token=settings.telegram_bot_token)
        chat_id = settings.telegram_authorized_user_id

        # 이미지가 있으면 이미지와 함께 전송
        if image_paths:
            for i, image_path in enumerate(image_paths):
                try:
                    with open(image_path, 'rb') as photo:
                        # 첫 번째 이미지에만 캡션 추가
                        caption = message[:1024] if i == 0 else None
                        await bot.send_photo(
                            chat_id=chat_id,
                            photo=photo,
                            caption=caption,
                        )
                except FileNotFoundError:
                    logger.warning(f"Image not found: {image_path}")
                except Exception as e:
                    logger.warning(f"Failed to send image {image_path}: {e}")

            # 메시지가 1024자 초과면 나머지 텍스트 전송
            if len(message) > 1024:
                await bot.send_message(chat_id=chat_id, text=message[1024:])
        else:
            # 텍스트만 전송
            for i in range(0, len(message), 4000):
                await bot.send_message(chat_id=chat_id, text=message[i:i+4000])

    except Exception as e:
        logger.error(f"Failed to send Telegram notification: {e}")


