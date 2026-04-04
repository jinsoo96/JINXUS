"""WaveNoter Cloud Sync — JX_SECRETARY 10분 루틴

WaveNoter 클라우드(app.wavenote.ai)에서 새 녹음을 확인하고
화이트보드에 메모로 등록하는 모듈.

Playwright MCP를 통해 브라우저 자동화로 접근.
실제 MCP 호출은 미션 시스템을 통해 JX_SECRETARY가 실행.
이 모듈은 루틴 등록 + 미션 템플릿 정의 담당.
"""
import asyncio
import logging
import time
from typing import Optional

logger = logging.getLogger(__name__)

# 루틴 식별자 (중복 등록 방지)
WAVENOTE_ROUTINE_NAME = "wavenote-sync"
WAVENOTE_ROUTINE_CRON = "*/10 * * * *"  # 10분마다

# 미션 템플릿: JX_SECRETARY가 Playwright로 WaveNoter 확인 → 화이트보드 등록
WAVENOTE_MISSION_TEMPLATE = """[WaveNoter 동기화 루틴]

1. Playwright(headless)로 https://app.wavenote.ai 접속
2. 로그인 상태 확인 (쿠키/세션 유지)
   - 로그인이 풀려있으면 작업 중단하고 "WaveNoter 로그인 필요" 보고
3. 노트 목록 페이지에서 최근 노트 확인
4. 이전에 동기화하지 않은 새 노트가 있으면:
   a. 각 노트의 제목과 전사된 텍스트 내용을 추출
   b. 화이트보드 API(POST /whiteboard)에 메모로 등록:
      - type: "memo"
      - title: 노트 제목
      - content: 전사 내용 전문
      - source: "wavenote"
      - tags: ["녹음", "wavenote"]
5. 동기화 결과를 간결하게 보고 (새 노트 N건 등록 / 새 노트 없음)

참고:
- 화이트보드 API 엔드포인트: POST http://localhost:19000/whiteboard
  body: {"type": "memo", "title": "...", "content": "...", "source": "wavenote", "tags": ["녹음", "wavenote"]}
- 이미 등록된 노트는 건너뛸 것 (제목 기준 중복 체크: GET /whiteboard → items에서 source=wavenote인 것 확인)
- 네트워크 오류 시 재시도 없이 다음 루틴에서 재확인
"""


async def ensure_wavenote_routine() -> Optional[str]:
    """서버 시작 시 WaveNoter 동기화 루틴이 등록되어 있는지 확인하고, 없으면 생성.

    Returns:
        routine_id 또는 None (이미 존재하면 기존 ID)
    """
    from jinxus.core.routine import get_routine_manager

    mgr = get_routine_manager()
    existing = await mgr.list_all()

    # 이미 등록된 루틴 확인
    for routine in existing:
        if routine.name == WAVENOTE_ROUTINE_NAME:
            logger.info(f"[WaveNoteSync] 루틴 이미 존재: {routine.id}")
            return routine.id

    # 신규 등록
    routine = await mgr.create(
        name=WAVENOTE_ROUTINE_NAME,
        cron_expr=WAVENOTE_ROUTINE_CRON,
        mission_template=WAVENOTE_MISSION_TEMPLATE,
        description="WaveNoter 클라우드에서 새 녹음 확인 → 화이트보드 메모 등록 (10분 주기)",
        assigned_agent="JX_SECRETARY",
        concurrency_policy="skip_if_active",
    )

    logger.info(f"[WaveNoteSync] 루틴 등록 완료: {routine.id} (cron={WAVENOTE_ROUTINE_CRON})")
    return routine.id
