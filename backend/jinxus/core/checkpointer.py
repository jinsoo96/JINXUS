"""LangGraph Checkpointer 생성 모듈 (B-4)

그래프 실행 상태를 영속화하여 서버 재시작 시 마지막 노드부터 재개 가능.
- persistent=True: SqliteSaver 사용 (langgraph-checkpoint-sqlite 필요)
- SqliteSaver 미설치 시 MemorySaver 폴백
"""
import logging
from pathlib import Path

from langgraph.checkpoint.memory import MemorySaver

logger = logging.getLogger(__name__)


def create_checkpointer(
    storage_path: Path | str | None = None,
    persistent: bool = True,
    db_name: str = "langgraph_checkpoints.db",
):
    """LangGraph 체크포인터 생성

    Args:
        storage_path: SQLite DB를 저장할 디렉토리 경로
        persistent: True면 SqliteSaver 시도, False면 MemorySaver
        db_name: SQLite DB 파일명

    Returns:
        BaseCheckpointSaver 인스턴스
    """
    if persistent and storage_path:
        try:
            from langgraph.checkpoint.sqlite import SqliteSaver

            path = Path(storage_path)
            path.mkdir(parents=True, exist_ok=True)
            db_path = path / db_name
            logger.info("SqliteSaver 사용: %s", db_path)
            return SqliteSaver.from_conn_string(str(db_path))
        except ImportError:
            logger.warning(
                "langgraph-checkpoint-sqlite 미설치 — MemorySaver 폴백"
            )

    logger.info("MemorySaver 사용 (인메모리)")
    return MemorySaver()
