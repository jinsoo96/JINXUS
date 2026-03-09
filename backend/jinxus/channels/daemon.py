"""JINXUS Daemon - 24시간 백그라운드 자율 작동

데스크탑에서 상시 실행되어 스케줄 작업 처리 및 자율 개선 수행.

사용법:
    # 포어그라운드 실행
    python -m jinxus.channels.daemon

    # 백그라운드 실행 (Unix)
    nohup python -m jinxus.channels.daemon &

    # 상태 확인
    python -m jinxus.channels.daemon --status

기능:
    - 스케줄 작업 자동 실행 (APScheduler)
    - 백그라운드 장기 작업 큐
    - 자가 강화 주기적 실행 (JinxLoop)
    - 헬스체크 및 텔레그램 알림
    - 서버 재시작 시 작업 복구
"""
import asyncio
import argparse
import logging
import signal
from datetime import datetime
from typing import Optional, Dict, Any

from jinxus.config import get_settings
from jinxus.core.orchestrator import get_orchestrator
from jinxus.tools.scheduler import Scheduler
from jinxus.channels.telegram_bot import send_notification

logger = logging.getLogger(__name__)


class JinxusDaemon:
    """JINXUS 24시간 백그라운드 데몬"""

    def __init__(self):
        self._orchestrator = None
        self._scheduler: Optional[Scheduler] = None
        self._running = False
        self._running_tasks: Dict[str, asyncio.Task] = {}
        self._start_time: Optional[datetime] = None
        self._settings = get_settings()

        # 헬스체크 간격 (초)
        self._health_check_interval = 60
        # 자가 강화 간격 (초) - 기본 6시간
        self._improvement_interval = 6 * 60 * 60

    async def initialize(self) -> None:
        """데몬 초기화"""
        logger.info("JINXUS Daemon 초기화 중...")

        # 오케스트레이터 초기화
        self._orchestrator = get_orchestrator()
        await self._orchestrator.initialize()

        # 스케줄러 초기화 및 복구
        self._scheduler = Scheduler()
        await self._scheduler.start()
        await self._scheduler.restore_from_db(
            execution_callback=self._execute_scheduled_task
        )

        self._start_time = datetime.now()
        logger.info("JINXUS Daemon 초기화 완료")

    async def start(self) -> None:
        """데몬 시작"""
        await self.initialize()

        self._running = True
        logger.info("JINXUS Daemon 시작됨. 대기 중...")

        # 시작 알림
        await send_notification(
            "🚀 JINXUS Daemon 시작됨\n"
            f"시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )

        # 백그라운드 태스크 시작
        tasks = [
            asyncio.create_task(self._health_check_loop()),
            asyncio.create_task(self._improvement_loop()),
            asyncio.create_task(self._keep_alive()),
        ]

        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            logger.info("Daemon 종료 신호 수신")
        finally:
            await self.stop()

    async def stop(self) -> None:
        """데몬 종료"""
        self._running = False
        logger.info("JINXUS Daemon 종료 중...")

        # 실행 중인 작업 취소
        for task_id, task in self._running_tasks.items():
            if not task.done():
                task.cancel()

        # 스케줄러 종료
        if self._scheduler:
            self._scheduler.shutdown()

        # 종료 알림
        await send_notification("🛑 JINXUS Daemon 종료됨")

        logger.info("JINXUS Daemon 종료 완료")

    async def _keep_alive(self) -> None:
        """메인 루프 - 프로세스 유지"""
        while self._running:
            await asyncio.sleep(1)

    async def _health_check_loop(self) -> None:
        """헬스체크 루프 - 인프라 상태 모니터링"""
        while self._running:
            try:
                await asyncio.sleep(self._health_check_interval)

                if not self._orchestrator:
                    continue

                health = await self._orchestrator.get_system_status()

                # 연결 문제 감지 시 알림
                if not health.get("redis_connected"):
                    await send_notification("⚠️ Redis 연결 끊김 감지!")
                    logger.warning("Redis connection lost")

                if not health.get("qdrant_connected"):
                    await send_notification("⚠️ Qdrant 연결 끊김 감지!")
                    logger.warning("Qdrant connection lost")

            except Exception as e:
                logger.error(f"Health check error: {e}")

    async def _improvement_loop(self) -> None:
        """자가 강화 루프 - JinxLoop 주기적 실행"""
        while self._running:
            try:
                await asyncio.sleep(self._improvement_interval)

                if not self._running:
                    break

                logger.info("자가 강화 사이클 시작...")

                try:
                    from jinxus.core.jinx_loop import get_jinx_loop
                    jinx_loop = get_jinx_loop()
                    results = await jinx_loop.run_improvement_cycle()

                    if results:
                        improved_agents = [
                            agent for agent, res in results.items()
                            if res.get("status") == "improved"
                        ]

                        if improved_agents:
                            await send_notification(
                                f"🔄 자가 강화 완료\n"
                                f"개선된 에이전트: {', '.join(improved_agents)}"
                            )
                            logger.info(f"Improvement cycle completed: {improved_agents}")

                except Exception as e:
                    logger.error(f"Improvement cycle error: {e}")

            except Exception as e:
                logger.error(f"Improvement loop error: {e}")

    async def _execute_scheduled_task(self, task_description: str, job_name: str) -> None:
        """스케줄 작업 실행 콜백"""
        logger.info(f"스케줄 작업 실행: {job_name}")

        try:
            if not self._orchestrator:
                self._orchestrator = get_orchestrator()
                await self._orchestrator.initialize()

            result = await self._orchestrator.run_task(
                user_input=task_description,
                session_id=f"scheduled_{job_name}",
            )

            response = result.get("response", "완료")[:1500]
            await send_notification(
                f"✅ [스케줄 작업 완료]\n"
                f"작업: {job_name}\n\n"
                f"결과:\n{response}"
            )

        except Exception as e:
            logger.error(f"Scheduled task error ({job_name}): {e}")
            await send_notification(
                f"❌ [스케줄 작업 실패]\n"
                f"작업: {job_name}\n"
                f"오류: {str(e)[:300]}"
            )

    async def submit_background_task(
        self, task_description: str, notify: bool = True
    ) -> str:
        """백그라운드 작업 제출

        Args:
            task_description: 작업 내용
            notify: 완료 시 텔레그램 알림 여부

        Returns:
            task_id: 작업 ID
        """
        import uuid
        task_id = str(uuid.uuid4())[:8]

        async def _run():
            try:
                if notify:
                    await send_notification(
                        f"🚀 백그라운드 작업 시작\n"
                        f"ID: {task_id}\n"
                        f"작업: {task_description[:100]}"
                    )

                result = await self._orchestrator.run_task(
                    user_input=task_description,
                    session_id=f"background_{task_id}",
                )

                if notify:
                    response = result.get("response", "완료")[:1500]
                    agents = result.get("agents_used", [])
                    await send_notification(
                        f"✅ 백그라운드 작업 완료\n"
                        f"ID: {task_id}\n"
                        f"에이전트: {', '.join(agents) if agents else 'CORE'}\n\n"
                        f"결과:\n{response}"
                    )

            except Exception as e:
                logger.error(f"Background task error ({task_id}): {e}")
                if notify:
                    await send_notification(
                        f"❌ 백그라운드 작업 실패\n"
                        f"ID: {task_id}\n"
                        f"오류: {str(e)[:300]}"
                    )
            finally:
                self._running_tasks.pop(task_id, None)

        task = asyncio.create_task(_run())
        self._running_tasks[task_id] = task

        return task_id

    def get_status(self) -> Dict[str, Any]:
        """데몬 상태 조회"""
        uptime = None
        if self._start_time:
            uptime = (datetime.now() - self._start_time).total_seconds()

        return {
            "running": self._running,
            "start_time": self._start_time.isoformat() if self._start_time else None,
            "uptime_seconds": uptime,
            "active_tasks": len(self._running_tasks),
            "task_ids": list(self._running_tasks.keys()),
        }


# 전역 데몬 인스턴스
_daemon: Optional[JinxusDaemon] = None


def get_daemon() -> JinxusDaemon:
    """데몬 싱글톤"""
    global _daemon
    if _daemon is None:
        _daemon = JinxusDaemon()
    return _daemon


async def run_daemon():
    """데몬 실행"""
    daemon = get_daemon()

    # 시그널 핸들러
    def signal_handler(sig, frame):
        logger.info(f"Signal {sig} received, stopping daemon...")
        asyncio.create_task(daemon.stop())

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    await daemon.start()


def main():
    """CLI 진입점"""
    parser = argparse.ArgumentParser(description="JINXUS Daemon")
    parser.add_argument(
        "--status", action="store_true", help="데몬 상태 확인"
    )
    parser.add_argument(
        "--health-interval", type=int, default=60,
        help="헬스체크 간격 (초)"
    )
    parser.add_argument(
        "--improvement-interval", type=int, default=21600,
        help="자가 강화 간격 (초, 기본 6시간)"
    )
    args = parser.parse_args()

    if args.status:
        daemon = get_daemon()
        status = daemon.get_status()
        print(f"Daemon Status: {status}")
        return

    # 로깅 설정
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    print("JINXUS Daemon 시작 중...")
    print("종료: Ctrl+C")
    print("-" * 50)

    asyncio.run(run_daemon())


if __name__ == "__main__":
    main()
