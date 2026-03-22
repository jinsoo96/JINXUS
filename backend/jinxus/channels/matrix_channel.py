"""Matrix Application Service 채널 모듈

에이전트들이 Matrix 룸에서 실제 사용자처럼 메시지를 주고받는다.
각 에이전트는 독립적인 Matrix 계정(@jx_coder:100.75.83.105 등)을 가진다.

## 아키텍처
- Synapse AS API: `?user_id=@agent:server` 파라미터로 에이전트 신원 impersonation
- JINXUS_CORE는 @jinxus_bot, 나머지 에이전트는 @jx_{코드소문자}: 형태
- 진수가 Matrix 룸에 메시지 → Synapse가 /matrix/transactions로 push → AgentReactor 트리거
"""
import asyncio
import logging
import uuid
from typing import Optional, Dict
from functools import lru_cache

import aiohttp

from jinxus.config import get_settings

logger = logging.getLogger(__name__)

# agent_code → Matrix localpart 매핑
def agent_to_localpart(agent_code: str) -> str:
    """에이전트 코드 → Matrix localpart
    예: JINXUS_CORE → jinxus_bot, JX_CODER → jx_coder
    """
    if agent_code == "JINXUS_CORE":
        return "jinxus_bot"
    return agent_code.lower().replace("_", "_")  # JX_CODER → jx_coder


# 채널 이름 → Matrix 룸 별칭 매핑
CHANNEL_TO_ROOM_ALIAS = {
    "general":     "#jinxus-general",
    "engineering": "#jinxus-engineering",
    "research":    "#jinxus-research",
    "ops":         "#jinxus-ops",
    "planning":    "#jinxus-planning",
}


class MatrixAS:
    """Matrix Application Service 클라이언트

    Synapse AS 토큰을 사용해 에이전트 가상 계정으로 메시지 전송.
    """

    def __init__(self):
        settings = get_settings()
        self._hs_url = settings.matrix_hs_url
        self._as_token = settings.matrix_as_token
        self._hs_token = settings.matrix_hs_token
        self._server_name = settings.matrix_server_name
        self._session: Optional[aiohttp.ClientSession] = None
        # 룸 별칭 → 룸 ID 캐시
        self._room_id_cache: Dict[str, str] = {}
        self._registered: set = set()

    def _session_obj(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={"Authorization": f"Bearer {self._as_token}"}
            )
        return self._session

    def _user_id(self, localpart: str) -> str:
        return f"@{localpart}:{self._server_name}"

    # ── 계정 관리 ──────────────────────────────────────────────────

    async def ensure_registered(self, localpart: str) -> bool:
        """가상 계정 등록 (이미 있으면 무시). 성공 시 True 반환."""
        if localpart in self._registered:
            return True
        session = self._session_obj()
        try:
            # AS 유저 등록: body에 username 명시, ?user_id 파라미터 없음
            async with session.post(
                f"{self._hs_url}/_matrix/client/v3/register",
                json={"type": "m.login.application_service", "username": localpart},
            ) as resp:
                text = await resp.text()
                if resp.status in (200, 400):  # 400 = M_USER_IN_USE = 이미 존재
                    self._registered.add(localpart)
                    return True
                logger.warning(f"[Matrix] register {localpart}: {resp.status} {text[:150]}")
                return False
        except Exception as e:
            logger.warning(f"[Matrix] register 실패 {localpart}: {e}")
            return False

    async def set_display_name(self, localpart: str, display_name: str) -> None:
        from urllib.parse import quote
        import yarl
        user_id = self._user_id(localpart)
        encoded_user_id = quote(user_id, safe="")
        url = yarl.URL(
            f"{self._hs_url}/_matrix/client/v3/profile/{encoded_user_id}/displayname?user_id={quote(user_id, safe='')}",
            encoded=True,
        )
        session = self._session_obj()
        try:
            async with session.put(url, json={"displayname": display_name}) as resp:
                if resp.status not in (200, 204):
                    text = await resp.text()
                    logger.debug(f"[Matrix] set_display_name {localpart}: {resp.status} {text[:80]}")
        except Exception as e:
            logger.warning(f"[Matrix] display_name 실패 {localpart}: {e}")

    # ── 룸 관리 ──────────────────────────────────────────────────

    async def get_or_create_room(self, alias_localpart: str, display_name: str) -> str:
        """룸 별칭으로 룸 ID 조회, 없으면 생성"""
        from urllib.parse import quote
        import yarl
        alias = f"#{alias_localpart}:{self._server_name}"
        if alias in self._room_id_cache:
            return self._room_id_cache[alias]

        session = self._session_obj()
        bot_user_id = self._user_id("jinxus_bot")
        encoded_alias = quote(alias, safe="")
        # aiohttp가 % 이중 인코딩 하지 않도록 yarl.URL(encoded=True) 사용
        dir_url = yarl.URL(
            f"{self._hs_url}/_matrix/client/v3/directory/room/{encoded_alias}?user_id={quote(bot_user_id, safe='')}",
            encoded=True,
        )

        async def _lookup() -> str:
            """별칭으로 기존 룸 ID 조회"""
            try:
                async with session.get(dir_url) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return data.get("room_id", "")
            except Exception as e:
                logger.debug(f"Matrix 룸 별칭 조회 실패: {e}")
            return ""

        # 조회 먼저
        room_id = await _lookup()
        if room_id:
            self._room_id_cache[alias] = room_id
            return room_id

        # 없으면 생성
        try:
            async with session.post(
                f"{self._hs_url}/_matrix/client/v3/createRoom",
                params={"user_id": bot_user_id},
                json={
                    "room_alias_name": alias_localpart,
                    "name": display_name,
                    "topic": f"JINXUS {display_name} 채널",
                    "preset": "public_chat",
                },
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    room_id = data["room_id"]
                    self._room_id_cache[alias] = room_id
                    logger.info(f"[Matrix] 룸 생성: {display_name} ({room_id})")
                    return room_id
                text = await resp.text()
                if "M_ROOM_IN_USE" in text:
                    # 이미 존재 — 다시 조회
                    room_id = await _lookup()
                    if room_id:
                        self._room_id_cache[alias] = room_id
                        return room_id
                logger.error(f"[Matrix] 룸 생성 실패: {resp.status} {text[:200]}")
        except Exception as e:
            logger.error(f"[Matrix] 룸 생성 예외: {e}")

        return ""

    async def join_room(self, localpart: str, room_id: str) -> None:
        """에이전트를 룸에 참가"""
        from urllib.parse import quote
        import yarl
        user_id = self._user_id(localpart)
        encoded_room_id = quote(room_id, safe="")
        url = yarl.URL(
            f"{self._hs_url}/_matrix/client/v3/join/{encoded_room_id}?user_id={quote(user_id, safe='')}",
            encoded=True,
        )
        session = self._session_obj()
        try:
            async with session.post(url, json={}) as resp:
                if resp.status not in (200, 400):
                    text = await resp.text()
                    logger.debug(f"[Matrix] join_room {localpart}: {resp.status} {text[:80]}")
        except Exception as e:
            logger.warning(f"[Matrix] join 실패 {localpart}: {e}")

    # ── 메시지 전송 ──────────────────────────────────────────────

    async def send_message(self, agent_code: str, room_id: str, text: str) -> None:
        """에이전트 계정으로 메시지 전송"""
        from urllib.parse import quote
        import yarl
        localpart = agent_to_localpart(agent_code)
        user_id = self._user_id(localpart)
        tx_id = uuid.uuid4().hex
        encoded_room_id = quote(room_id, safe="")
        url = yarl.URL(
            f"{self._hs_url}/_matrix/client/v3/rooms/{encoded_room_id}/send/m.room.message/{tx_id}?user_id={quote(user_id, safe='')}",
            encoded=True,
        )
        session = self._session_obj()
        try:
            async with session.put(url, json={"msgtype": "m.text", "body": text}) as resp:
                if resp.status != 200:
                    text_resp = await resp.text()
                    logger.warning(f"[Matrix] send {agent_code}: {resp.status} {text_resp[:100]}")
        except Exception as e:
            logger.warning(f"[Matrix] send 실패 {agent_code}: {e}")

    async def send_to_channel(self, agent_code: str, channel: str, text: str) -> None:
        """채널 이름으로 메시지 전송 (룸 별칭 자동 조회)"""
        alias_localpart = f"jinxus-{channel}"
        channel_names = {
            "general": "🏢 전체",
            "engineering": "💻 개발부서",
            "research": "🔬 리서치부서",
            "ops": "🖥️ 운영부서",
            "planning": "📋 플래닝",
        }
        display_name = channel_names.get(channel, channel)
        room_id = await self.get_or_create_room(alias_localpart, display_name)
        if room_id:
            await self.send_message(agent_code, room_id, text)

    # ── 초기화 ──────────────────────────────────────────────────

    async def setup_all_agents(self) -> None:
        """모든 에이전트 계정 등록 + 이름 설정 + 룸 참가 + room_id→channel 매핑 등록"""
        from jinxus.agents.personas import PERSONAS
        from jinxus.api.routers.matrix import register_room_channel

        # 채널별 룸 ID 미리 생성 + 매핑 등록
        rooms: Dict[str, str] = {}
        for ch, display in {
            "general":     "🏢 전체",
            "engineering": "💻 개발부서",
            "research":    "🔬 리서치부서",
            "ops":         "🖥️ 운영부서",
            "planning":    "📋 플래닝",
            "marketing":   "📣 마케팅부서",
        }.items():
            room_id = await self.get_or_create_room(f"jinxus-{ch}", display)
            if room_id:
                rooms[ch] = room_id
                register_room_channel(room_id, ch)  # Synapse 이벤트 → 채널 매핑
                logger.info(f"[Matrix] 룸 매핑: #{ch} → {room_id}")

        # 에이전트마다 계정 등록 + 룸 참가
        for code, persona in PERSONAS.items():
            localpart = agent_to_localpart(code)
            await self.ensure_registered(localpart)
            await self.set_display_name(localpart, f"{persona.emoji} {persona.korean_name} ({persona.role})")
            for ch in persona.channels:
                if ch in rooms:
                    await self.join_room(localpart, rooms[ch])

        logger.info(f"[Matrix] 에이전트 {len(PERSONAS)}명 셋업 완료")

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()


# ── 싱글톤 ────────────────────────────────────────────────────────

_matrix_as: Optional[MatrixAS] = None


def get_matrix_as() -> MatrixAS:
    global _matrix_as
    if _matrix_as is None:
        _matrix_as = MatrixAS()
    return _matrix_as
