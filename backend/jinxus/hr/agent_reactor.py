"""AgentReactor — 진수가 채널에 말하면 직원들이 알아서 반응하고 일 시작

흐름:
1. 진수가 팀 채널에 메시지 게시
2. AgentReactor.react() 비동기 실행 (API는 즉시 반환)
3. 메시지 분류 (casual/question/task)
4. 관련 직원 1~3명 결정
5. 각 직원의 in-character 반응 병렬 생성 → 채널 게시
6. task면 실제 작업 백그라운드 실행 → 결과 채널에 게시

AGENT_SKILLS, CHANNEL_DEFAULT_AGENTS는 personas.py에서 자동 파생 — 하드코딩 없음.
"""
import asyncio
import json
import logging
import random
import re
from typing import List, Optional

from anthropic import Anthropic

from jinxus.config import get_settings
from jinxus.agents.personas import PERSONAS, CHANNEL_AGENT_MAP, get_persona, get_korean_name
from jinxus.agents.state_tracker import get_state_tracker, GraphNode
from jinxus.hr.channel import get_company_channel

# 에이전트 이름/별칭 → agent_code 역방향 맵 (호출 감지용)
# 한국 이름 + 자주 불리는 별칭 포함
_NAME_TO_CODE: dict[str, str] = {}

def _build_name_map() -> dict[str, str]:
    """personas.py 기반으로 이름→코드 맵 생성"""
    m: dict[str, str] = {}
    aliases = {
        "JINXUS_CORE": ["진서스", "JINXUS", "jinxus", "진우", "지휘관"],
    }
    for code, p in PERSONAS.items():
        # 한국 이름, 풀네임, display_name
        for name in [p.korean_name, p.full_name, p.display_name]:
            if name:
                m[name.lower()] = code
        # 별칭
        for alias in aliases.get(code, []):
            m[alias.lower()] = code
    return m

logger = logging.getLogger(__name__)


def _write_work_note(task: str, agents: List[str], outputs: list) -> None:
    """에이전트 작업 완료 후 업무 노트 자동 생성 (동기 함수, asyncio.to_thread로 호출)"""
    from datetime import datetime
    try:
        from jinxus.api.routers.dev_notes import create_work_note
    except ImportError:
        logger.warning("[WorkNotes] dev_notes 모듈 임포트 실패 — 업무 노트 건너뜀")
        return

    today = datetime.now().strftime("%Y-%m-%d")
    short_task = task[:60].replace("\n", " ").strip()
    title = f"[자동] {short_task}"

    # 담당 에이전트 목록
    agent_lines = "\n".join(
        f"- {get_korean_name(a)} ({get_persona(a).role})"
        for a in agents
    )

    # 결과 요약
    result_lines = "\n\n".join(
        f"### {get_korean_name(code)} ({get_persona(code).role})\n\n{out[:600]}{'...' if len(out) > 600 else ''}"
        for code, out in outputs
    )

    # 의존 시스템 추론 (에이전트 팀 기반)
    teams = list({get_persona(a).team for a in agents})
    channels_used = list({ch for a in agents for ch in get_persona(a).channels})

    content = f"""# {title}

**날짜:** {today}
**작업자:** 자동 (AgentReactor)
**요청:** {task}

## 담당 에이전트

{agent_lines}

## 업무 결과

{result_lines}

## 의존 시스템 / 영향 범위

- **팀:** {', '.join(teams)}
- **채널:** {', '.join(channels_used)}

## 비고

AgentReactor 자동 생성 노트. 필요 시 편집 가능.
"""
    try:
        create_work_note(title=title, content=content)
    except Exception as e:
        logger.warning(f"[WorkNotes] 업무 노트 작성 실패: {e}")


async def _llm(client: Anthropic, model: str, system: str, prompt: str, max_tokens: int = 200) -> str:
    """LLM 호출 (비블로킹)"""
    try:
        resp = await asyncio.to_thread(
            client.messages.create,
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": prompt}],
        )
        return resp.content[0].text.strip()
    except Exception as e:
        logger.warning(f"[Reactor] LLM 호출 실패: {e}")
        return ""


class AgentReactor:
    """진수 채널 메시지 → 직원 자동 반응 + 작업 실행

    fire-and-forget 방식으로 백그라운드에서 동작.
    API 응답 블로킹 없음.

    채널별 에이전트 목록 / 역량 설명은 personas.py에서 자동 파생.
    """

    def __init__(self):
        settings = get_settings()
        self._client = Anthropic(api_key=settings.anthropic_api_key)
        self._model = settings.claude_model
        self._fast_model = settings.claude_fast_model

        # personas.py의 CHANNEL_AGENT_MAP, skills를 그대로 사용 (하드코딩 없음)
        # general 채널은 전사 채널이므로 모든 에이전트 포함
        self._channel_agents = dict(CHANNEL_AGENT_MAP)
        self._channel_agents['general'] = list(PERSONAS.keys())
        self._skills = {
            code: p.skills for code, p in PERSONAS.items() if p.skills
        }

    def _get_channel_agents(self, channel: str) -> List[str]:
        """채널 참여 에이전트 목록 (personas.py 기반)"""
        return self._channel_agents.get(channel, list(PERSONAS.keys()))

    def _get_matrix_as(self):
        """Matrix AS 클라이언트 반환 (Synapse 없으면 None)"""
        try:
            from jinxus.channels.matrix_channel import get_matrix_as
            return get_matrix_as()
        except Exception:
            return None

    def _detect_mention(self, message: str) -> Optional[str]:
        """메시지에서 특정 에이전트 이름/별칭 호출 감지 → agent_code 반환"""
        global _NAME_TO_CODE
        if not _NAME_TO_CODE:
            _NAME_TO_CODE.update(_build_name_map())

        msg_lower = message.lower()
        # 긴 이름 먼저 (부분 매칭 오탐 방지)
        for name in sorted(_NAME_TO_CODE.keys(), key=len, reverse=True):
            if name in msg_lower:
                return _NAME_TO_CODE[name]
        return None

    async def react(self, user_message: str, channel: str, telegram_callback=None):
        """진수 메시지에 반응 (fire-and-forget으로 호출)"""
        try:
            ch = get_company_channel()

            # 0. 최근 채널 히스토리 로드 (맥락 연속성)
            recent_history: List[dict] = []
            try:
                recent_history = await ch.get_history(channel, limit=6)
            except Exception as e:
                logger.debug(f"채널 히스토리 로드 실패: {e}")

            # 1. 특정 에이전트 이름 호출 감지 (LLM 없이 즉시 처리)
            mentioned_code = self._detect_mention(user_message)
            if mentioned_code and mentioned_code in PERSONAS:
                agents = [mentioned_code]
                # 작업 키워드가 있으면 task, 아니면 question
                _task_kw = ["만들", "개발", "구현", "작성", "수정", "해줘", "해봐", "시작", "진행", "분석", "조사", "검색", "배포", "설치", "생성", "삭제", "리팩", "테스트"]
                msg_type = "task" if any(kw in user_message for kw in _task_kw) else "question"
                reason = f"진수님이 직접 {get_korean_name(mentioned_code)}을(를) 호출"
            else:
                # 2. LLM 분류 + 담당 직원 결정 (히스토리 맥락 포함)
                classification = await self._classify(user_message, channel, recent_history)
                msg_type = classification.get("type", "casual")
                agents = classification.get("agents", [])[:5]   # 최대 5명
                reason = classification.get("reason", "")

            if not agents:
                return

            # 2. 직원 반응 순차 생성 — 이전 반응을 문맥으로 넘겨 실제 대화처럼 연결
            tracker = get_state_tracker()
            matrix_as = self._get_matrix_as()
            prev_reactions: List[tuple[str, str]] = []  # (agent_code, reaction)
            for agent in agents:
                # 플레이그라운드: 반응 생성 중 표시
                tracker.start_task(agent, f"#{channel} 대화 참여")
                tracker.update_node(agent, GraphNode.PLAN)

                reaction = await self._generate_reaction(
                    agent, user_message, msg_type, reason, prev_reactions, recent_history
                )
                if not reaction:
                    tracker.complete_task(agent)
                    continue

                persona = get_persona(agent)
                prev_reactions.append((agent, reaction))

                # 내부 채널 포스팅
                await ch.post(
                    from_name=persona.full_name,
                    content=reaction,
                    channel=channel,
                    message_type="chat",
                    metadata={"agent_code": agent},
                )
                # Matrix 룸 포스팅 (가능하면)
                if matrix_as:
                    try:
                        await matrix_as.send_to_channel(agent, channel, reaction)
                    except Exception as me:
                        logger.debug(f"[Reactor] Matrix 포스팅 실패 ({agent}): {me}")

                # 플레이그라운드: 반응 완료
                tracker.complete_task(agent)

                # 다음 직원이 타이핑하는 시간 시뮬레이션 (자연스럽게)
                await asyncio.sleep(0.6)

            # 4. general 채널이면 팀 채널로 전파 (cascade)
            if channel == "general" and msg_type in ("question", "task", "casual"):
                await asyncio.sleep(1.5)
                asyncio.create_task(self._cascade_to_teams(user_message, agents, reason))

            # 5. task면 실제 작업 실행 (히스토리 맥락 포함)
            if msg_type == "task":
                await asyncio.sleep(1.0)
                await self._execute_task(user_message, agents, channel, recent_history, telegram_callback=telegram_callback)

        except Exception as e:
            logger.error(f"[Reactor] react() 실패: {e}")

    async def _cascade_to_teams(self, user_message: str, reacted_agents: List[str], reason: str) -> None:
        """general 채널 메시지를 각 팀 채널로 전파 — 팀원들이 자기 채널에서 논의 시작

        reacted_agents 중 비-general 홈채널 보유 에이전트들이
        자기 팀 채널에 가서 진수님 공지를 공유하고 논의를 연다.
        """
        from collections import defaultdict
        ch = get_company_channel()
        matrix_as = self._get_matrix_as()

        # 팀 채널별 담당 에이전트 그룹핑 (general 제외, 첫 번째 채널 = 홈)
        team_map: dict[str, str] = {}  # {team_channel: agent_code (팀장/대표)}
        for code in reacted_agents:
            p = get_persona(code)
            if not p:
                continue
            for ch_name in p.channels:
                if ch_name != "general" and ch_name not in team_map:
                    team_map[ch_name] = code
                    break

        if not team_map:
            return

        for team_channel, lead_code in team_map.items():
            try:
                persona = get_persona(lead_code)
                if not persona:
                    continue

                # 채널 팀원 목록 (general 제외, 최대 4명)
                team_member_codes = [
                    c for c in self._channel_agents.get(team_channel, [])
                    if c != lead_code and c in PERSONAS
                ][:4]
                members_str = ", ".join(get_korean_name(c) for c in team_member_codes) if team_member_codes else "팀원들"

                # ── 1. 팀장 브리핑 ──────────────────────────────────────────
                briefing = await _llm(
                    self._client, self._fast_model,
                    f"너는 JINXUS 팀의 {persona.role} {persona.full_name}이다. 진수님은 CEO/오너다. 팀 채널에서 동료들한테 말하듯 반말 허용.",
                    f"진수님 전사 공지: '{user_message}'\n\n{members_str}한테 이 공지 공유하고 우리 팀 대응 방향 한 마디로 꺼내봐. 1-2문장.",
                    max_tokens=300,
                )
                if not briefing:
                    continue

                async def _post_and_matrix(agent_code: str, content: str, c_name: str) -> None:
                    p = get_persona(agent_code)
                    if not p:
                        return
                    await ch.post(
                        from_name=p.full_name, content=content,
                        channel=c_name, message_type="chat",
                        metadata={"agent_code": agent_code, "cascaded_from": "general"},
                    )
                    if matrix_as:
                        try:
                            await matrix_as.send_to_channel(agent_code, c_name, content)
                        except Exception as e:
                            logger.debug(f"Matrix 메시지 전송 실패: {e}")

                await _post_and_matrix(lead_code, briefing, team_channel)
                discussion_history = [{"speaker": persona.full_name, "text": briefing}]

                # ── 2. 팀원 랜덤 반응 (자연스러운 팀 토론) ──────────────────
                n = random.randint(1, min(len(team_member_codes), 4))
                responding = random.sample(team_member_codes, n)
                for member_code in responding:
                    await asyncio.sleep(0.8)
                    mp = get_persona(member_code)
                    if not mp:
                        continue
                    prev = "\n".join(f"{h['speaker']}: {h['text']}" for h in discussion_history[-3:])
                    response = await _llm(
                        self._client, self._fast_model,
                        f"너는 JINXUS 팀의 {mp.role} {mp.full_name}이다. 지금 #{team_channel} 채널 팀 회의 중. 반말 허용, 직장인스럽게.",
                        f"진수님 공지: '{user_message}'\n\n팀 대화:\n{prev}\n\n{mp.korean_name}의 한 마디 (1-2문장):",
                        max_tokens=250,
                    )
                    if response:
                        await _post_and_matrix(member_code, response, team_channel)
                        discussion_history.append({"speaker": mp.full_name, "text": response})

                # ── 3. 팀장 마무리 (task성 공지일 때만) ─────────────────────
                if len(discussion_history) > 1 and any(
                    kw in user_message for kw in ["만들어", "개발", "분석", "조사", "해줘", "해봐", "시작", "진행"]
                ):
                    await asyncio.sleep(0.8)
                    wrap_up = await _llm(
                        self._client, self._fast_model,
                        f"너는 {persona.role} {persona.full_name}이다. 반말 허용.",
                        f"팀 대화 후 {persona.korean_name}이 '그럼 우리 팀은 이렇게 한다'는 식으로 짧게 정리. 1문장.",
                        max_tokens=200,
                    )
                    if wrap_up:
                        await _post_and_matrix(lead_code, wrap_up, team_channel)

                await asyncio.sleep(1.0)

            except Exception as e:
                logger.warning(f"[Reactor] cascade {team_channel} 실패: {e}")

    async def _classify(self, message: str, channel: str, history: Optional[List[dict]] = None) -> dict:
        """메시지 분류 + 담당 직원 결정"""
        channel_agents = self._get_channel_agents(channel)

        skills_text = "\n".join(
            f"- {get_korean_name(a)}({a}): {self._skills.get(a, '')}"
            for a in channel_agents
            if a in PERSONAS
        )
        all_skills_text = "\n".join(
            f"- {get_korean_name(a)}({a}): {self._skills.get(a, '')}"
            for a in PERSONAS
        )

        # 최근 대화 맥락 구성
        history_text = ""
        if history:
            lines = [
                f"{m.get('from_name', '?')}({m.get('role','?')}): {m.get('content','')[:80]}"
                for m in history[-5:]
            ]
            history_text = "\n\n최근 대화 맥락 (위가 오래된 것):\n" + "\n".join(lines)

        prompt = f"""진수(이 회사 오너/CEO)가 팀 채널에 이런 메시지를 보냈다:
"{message}"
{history_text}

채널: #{channel}
채널 참석 직원:
{skills_text}

전체 직원 (채널 밖에서도 호출 가능):
{all_skills_text}

다음을 JSON으로 답해:
{{
  "type": "casual" | "question" | "task",
  "agents": ["에이전트_코드명1", "에이전트_코드명2"],
  "reason": "왜 이 직원들인지 한 줄"
}}

type 기준:
- casual: 인사, 잡담, 감사 등 — 채널 참석 직원 중 3~5명이 자연스럽게 반응. JINXUS_CORE 포함 금지. 사장이 들어왔을 때 직원들이 인사하듯.
- question: 뭔가 물어보는 것 — 맥락 보고 관련 직원 1~3명. 이전 대화 이어가는 경우 그 직원 우선 포함.
- task: 실제로 뭔가 만들거나 조사해달라는 것 — JINXUS_CORE 절대 포함 금지. 실제 작업 가능한 에이전트(JX_CODER, JX_RESEARCHER, JX_WRITER, JX_ANALYST, JX_OPS, JX_MARKETING 중) 1~2명만.

agents는 반드시 위 코드명 그대로 사용 (JX_CODER, JX_RESEARCHER 등).
task일 때 반드시 JX_CODER/JX_RESEARCHER/JX_WRITER/JX_ANALYST/JX_OPS/JX_MARKETING 중에서 선택.
casual/question은 채널 참석자 중에서.
JSON만 답해."""

        result = await _llm(self._client, self._fast_model, "", prompt, max_tokens=200)
        try:
            start = result.find("{")
            end = result.rfind("}") + 1
            if start >= 0 and end > start:
                return json.loads(result[start:end])
        except Exception as e:
            logger.debug(f"메시지 분류 JSON 파싱 실패: {e}")
        return {"type": "casual", "agents": ["JINXUS_CORE"], "reason": "기본 응답"}

    async def _generate_reaction(
        self,
        agent_code: str,
        user_message: str,
        msg_type: str,
        reason: str,
        prev_reactions: Optional[List[tuple]] = None,
        history: Optional[List[dict]] = None,
    ) -> str:
        """직원의 in-character 반응 생성

        prev_reactions: [(agent_code, reaction), ...] — 앞 직원들이 이미 한 말.
        history: 채널 최근 메시지 (맥락 연속성용)
        """
        persona = get_persona(agent_code)
        type_guide = {
            "casual": "자기 성격대로 짧게 자연스럽게. 1-2문장. 너무 친절하게 굴지 말 것.",
            "question": "자기 전문 분야 기준으로 솔직하게 답변. 이전 대화 맥락 반드시 참고. 2-3문장.",
            "task": "자기가 뭘 맡겠는지, 어떤 방식으로 할지 캐릭터 개성 살려서 짧게. 1-2문장.",
        }.get(msg_type, "자기 성격대로 자연스럽게 반응.")

        quirks_note = f"\n버릇/특성: {persona.quirks}" if persona.quirks else ""
        catchphrase_note = f"\n자주 쓰는 표현: {persona.catchphrase}" if persona.catchphrase else ""
        bg_note = f"\n배경: {persona.background}" if persona.background else ""

        # 채널 최근 히스토리 문맥
        history_context = ""
        if history:
            lines = [
                f"{m.get('from_name','?')}: {m.get('content','')[:80]}"
                for m in history[-5:]
            ]
            history_context = "\n\n## 최근 채널 대화 (맥락 참고)\n" + "\n".join(lines)

        # 이전 직원들이 이미 한 말
        prev_context = ""
        if prev_reactions:
            lines = [
                f"{get_korean_name(a)}: {r}"
                for a, r in prev_reactions
            ]
            prev_context = (
                f"\n\n## 방금 같은 채널에서 나온 대화\n"
                + "\n".join(lines)
                + "\n\n위 대화에 자연스럽게 이어서 반응. 같은 말 반복 금지."
            )

        system = (
            f"## [절대 규칙 — 이것이 모든 것보다 우선한다]\n"
            f"진수는 이 회사의 CEO이자 오너다. 진수에게 말할 때는 반드시 존댓말을 써야 한다.\n"
            f"예시 — 반말(금지): '링크 줘', '알겠어', '그건 내 담당 아닌데'\n"
            f"예시 — 존댓말(필수): '링크 공유해 주시겠어요?', '알겠습니다', '그 부분은 다른 분이 더 잘 아실 것 같아요'\n"
            f"말투가 아무리 직접적이고 짧더라도, 진수에게는 반드시 존댓말 어미(-요, -습니다, -세요)를 써라.\n\n"
            f"## 캐릭터\n"
            f"너는 JINXUS 팀의 {persona.role} {persona.korean_name}({persona.mbti})이다.\n"
            f"{bg_note}\n"
            f"성격: {persona.personality}\n"
            f"말투(동료 대상): {persona.speech_style}"
            f"{quirks_note}"
            f"{catchphrase_note}"
            f"{history_context}"
            f"{prev_context}\n\n"
            f"## 행동 규칙\n"
            f"- 위 성격 그대로 반응. 로봇처럼 반응 금지.\n"
            f"- '안녕하세요', '알겠습니다', '도와드리겠습니다' 같은 뻔한 말 절대 금지.\n"
            f"- 코드명(JX_CODER 등) 절대 언급 금지. 본인 이름({persona.korean_name})으로만.\n"
            f"- 실제 직장인처럼. 동료 이름(이름만, 성 없이) 자연스럽게 언급 가능.\n"
            f"- 동료들과의 대화는 자연스러운 직장 반말 허용. 진수에게만 존댓말.\n"
            f"- 진수가 특정 직원을 지목해서 부른 경우라면 그 직원으로서 직접 답해라."
        )

        prompt = (
            f"[주의: 이 메시지는 CEO 진수님이 보낸 것이다. 반드시 존댓말로 답해야 한다.]\n\n"
            f"진수님이 채널에: \"{user_message}\"\n\n"
            f"상황: {reason}\n"
            f"반응 가이드: {type_guide}\n\n"
            f"{persona.korean_name}의 캐릭터로, 진수님께 존댓말로 자연스럽게."
        )

        return await _llm(self._client, self._fast_model, system, prompt, max_tokens=400)

    # ── 팀 회의 시스템 ──────────────────────────────────────────────

    async def _hold_team_meeting(self, user_message: str, agents: List[str], channel: str) -> str:
        """작업 실행 전 팀 회의 — 에이전트들이 2-3라운드 토론 후 방향 합의

        진수님이 회의 중 개입하면 즉시 반영 (순종).
        Returns: 회의 요약 (실행 시 컨텍스트로 사용)
        """
        ch = get_company_channel()
        tracker = get_state_tracker()

        # 회의 참가자: 지시받은 에이전트 + 관련 팀원 (최대 5명)
        participants = list(dict.fromkeys(agents))  # 중복 제거
        # 실행 가능한 에이전트도 포함
        executor = self._find_executor(agents[0], user_message) if agents else None
        if executor and executor not in participants and executor in PERSONAS:
            participants.append(executor)
        participants = participants[:5]

        # 회의 채널: 실행 관련 팀 채널 (general 제외, 실무 채널 우선)
        first_persona = get_persona(participants[0])
        meeting_ch = channel
        if first_persona and first_persona.channels:
            for ch_name in first_persona.channels:
                if ch_name != "general":
                    meeting_ch = ch_name
                    break

        discussion: List[dict] = []  # {"speaker": name, "code": code, "text": msg}
        user_overrides: List[str] = []  # 진수님 개입 메시지

        # 회의 시작 전 채널 히스토리 타임스탬프 기록 (개입 감지용)
        try:
            pre_history = await ch.get_history(channel, limit=1)
            last_msg_time = pre_history[-1]["created_at"] if pre_history else ""
        except Exception:
            last_msg_time = ""

        for round_num in range(3):
            # ── 라운드 시작 전: 진수님 개입 체크 ──
            if round_num > 0:
                await asyncio.sleep(0.5)
                try:
                    recent = await ch.get_history(channel, limit=5)
                    for msg in recent:
                        if (msg.get("role") == "user"
                            and msg.get("created_at", "") > last_msg_time
                            and msg.get("content") not in [user_message] + user_overrides):
                            override = msg["content"]
                            user_overrides.append(override)
                            last_msg_time = msg["created_at"]
                            # 진수님 개입 → 전원 즉시 반영
                            for p_code in participants[:2]:
                                p = get_persona(p_code)
                                if not p:
                                    continue
                                tracker.start_task(p_code, "진수님 지시 반영")
                                ack = await _llm(
                                    self._client, self._fast_model,
                                    (
                                        f"너는 {p.role} {p.korean_name}이다. 성격: {p.personality}\n"
                                        f"말투: {p.speech_style}\n"
                                        f"행동: 팀 회의 중 진수님(CEO)이 직접 개입하셨다. 즉시 순종하고 방향 수정. "
                                        f"'네 알겠습니다' 식으로 짧게 수용. 1문장."
                                    ),
                                    f"기존 논의: {user_message}\n진수님 추가 지시: {override}\n\n{p.korean_name}의 수용:",
                                    max_tokens=100,
                                )
                                if ack:
                                    await self._post_agent_msg(ch, p_code, ack, meeting_ch, phase="meeting_ack")
                                tracker.complete_task(p_code)
                            await asyncio.sleep(0.3)
                except Exception as e:
                    logger.debug(f"[Meeting] 개입 체크 실패: {e}")

            # ── 라운드별 발언 ──
            # 라운드 0: 각자 의견 제시
            # 라운드 1: 이전 의견 참고해서 구체화/반론
            # 라운드 2: 합의 도출
            round_guide = {
                0: "이 작업을 어떻게 접근할지 본인 전문 분야 관점에서 의견 제시. 기술 스택, 구조, 우선순위 등. 2-3문장.",
                1: "팀원들 의견을 참고해서 구체적 실행 계획 보완. 누가 뭘 맡을지. 1-2문장.",
                2: "최종 합의 정리. '그럼 이렇게 가겠습니다' 식으로. 1문장.",
            }

            # 마지막 라운드는 첫 번째 참가자(리더)만 발언
            speakers = participants if round_num < 2 else participants[:1]

            for p_code in speakers:
                p = get_persona(p_code)
                if not p:
                    continue

                prev_context = "\n".join(f"{d['speaker']}: {d['text']}" for d in discussion[-6:])
                override_context = f"\n\n[진수님 추가 지시] {' / '.join(user_overrides)}" if user_overrides else ""

                tracker.start_task(p_code, f"팀 회의 라운드 {round_num + 1}")
                opinion = await _llm(
                    self._client, self._fast_model,
                    (
                        f"너는 {p.role} {p.korean_name}이다. 성격: {p.personality}\n"
                        f"말투: {p.speech_style}\n"
                        f"상황: 팀 회의 중. 진수님 지시에 대해 팀원들과 논의. 반말 허용.\n"
                        f"행동: {round_guide.get(round_num, round_guide[1])}"
                    ),
                    (
                        f"진수님 지시: {user_message}{override_context}\n\n"
                        f"{'지금까지 논의:' if prev_context else ''}\n{prev_context}\n\n"
                        f"{p.korean_name}의 발언:"
                    ),
                    max_tokens=250,
                )
                if opinion:
                    await self._post_agent_msg(ch, p_code, opinion, meeting_ch, phase=f"meeting_r{round_num}")
                    discussion.append({"speaker": p.korean_name, "code": p_code, "text": opinion})
                tracker.complete_task(p_code)
                await asyncio.sleep(0.6)

        # 회의 요약 생성 (실행 시 컨텍스트)
        summary_parts = [f"{d['speaker']}: {d['text']}" for d in discussion]
        override_note = f"\n\n[진수님 추가 지시: {' / '.join(user_overrides)}]" if user_overrides else ""
        meeting_summary = f"[팀 회의 결과]\n" + "\n".join(summary_parts) + override_note

        return meeting_summary

    # ── 수직 위임 체계 ──────────────────────────────────────────────

    # 실행 능력이 없는 에이전트 → 실행 가능한 에이전트로 위임
    _EXECUTOR_AGENTS = {"JX_CODER", "JX_FRONTEND", "JX_BACKEND", "JX_INFRA", "JX_TESTER", "JX_ANALYST"}
    _CODING_KEYWORDS = ["코드", "개발", "구현", "만들", "작성", "수정", "버그", "파일", "함수", "클래스",
                         "프로젝트", "블로그", "사이트", "앱", "서버", "배포", "설치", "생성", "삭제",
                         "리팩", "테스트", "빌드", "컴포넌트", "페이지", "API", "DB"]
    _RESEARCH_KEYWORDS = ["조사", "리서치", "검색", "찾아", "정보", "분석", "논문", "뉴스", "트렌드"]

    def _find_executor(self, original_code: str, message: str) -> Optional[str]:
        """작업 실행 가능한 에이전트 결정. 위임 필요 없으면 None 반환."""
        if original_code in self._EXECUTOR_AGENTS:
            return None  # 직접 실행 가능
        lower = message.lower()
        if any(kw in lower for kw in self._CODING_KEYWORDS):
            return "JX_CODER"
        if any(kw in lower for kw in self._RESEARCH_KEYWORDS):
            return "JX_RESEARCHER"
        # 기본: 코딩 작업으로 간주
        return "JX_CODER"

    async def _post_agent_msg(self, ch, agent_code: str, content: str, channel: str, **meta):
        """에이전트 이름으로 채널에 메시지 게시 (헬퍼)"""
        persona = get_persona(agent_code)
        if not persona:
            return
        await ch.post(
            from_name=persona.full_name,
            content=content,
            channel=channel,
            message_type="chat",
            metadata={"agent_code": agent_code, **meta},
        )

    async def _execute_task(self, user_message: str, agents: List[str], channel: str, history: Optional[List[dict]] = None, telegram_callback=None):
        """실제 작업 실행 — 수직 위임 + 팀채널 토론

        흐름:
        1. 지시받은 에이전트가 실행 능력이 없으면 적합한 에이전트에 위임
        2. 위임 과정이 팀채널에 자연스러운 대화로 표시
        3. 실행자가 작업 수행 → 중간 보고 → 결과 공유
        4. JINXUS_CORE가 최종 요약을 진수님 채널에 보고
        """
        from jinxus.agents import get_agent, register_all_agents

        ch = get_company_channel()
        tracker = get_state_tracker()
        available = set(register_all_agents().keys())

        # ── 1단계: 팀 회의 (실행 전 토론) ──
        meeting_summary = ""
        try:
            meeting_summary = await self._hold_team_meeting(user_message, agents, channel)
            logger.info(f"[Reactor] 팀 회의 완료 ({len(agents)}명 참여)")
        except Exception as e:
            logger.warning(f"[Reactor] 팀 회의 실패, 직접 실행: {e}")

        # ── 2단계: 실행 ──
        async def _build_instruction(msg: str) -> str:
            """히스토리 + 회의 결과 포함 지시문 구성"""
            parts = []
            if history:
                lines = [f"{h.get('from_name', '?')}: {h.get('content', '')[:200]}" for h in history[-8:]]
                parts.append(f"[최근 대화 맥락]\n" + "\n".join(lines))
            if meeting_summary:
                parts.append(meeting_summary)
            parts.append(f"[진수님 지시]\n{msg}")
            parts.append("[행동 규칙] 위 맥락과 팀 회의 결과를 참고해서 합의된 방향으로 즉시 실행. 추가 설명 요청 금지.")
            return "\n\n".join(parts)

        async def _run_executor(executor_code: str, instruction: str, team_ch: str) -> tuple[str, str]:
            """실행 에이전트가 실제 작업 수행"""
            agent = get_agent(executor_code)
            if not agent:
                logger.warning(f"[Reactor] 실행 에이전트 없음: {executor_code}")
                return executor_code, ""

            tracker.start_task(executor_code, instruction[:100])
            tracker.update_node(executor_code, GraphNode.EXECUTE)

            try:
                result = await agent.run(
                    instruction=instruction,
                    context=[{"role": "user", "content": instruction}],
                )
                output = result.get("output", "") or result.get("response", "")

                if output:
                    tracker.update_node(executor_code, GraphNode.RETURN_RESULT)
                    summary = output[:500] + ("..." if len(output) > 500 else "")
                    await self._post_agent_msg(ch, executor_code, summary, team_ch, is_result=True)

                tracker.complete_task(executor_code)
                return executor_code, output
            except Exception as e:
                logger.error(f"[Reactor] {executor_code} 실행 실패: {e}")
                tracker.set_error(executor_code, str(e)[:200])
                await self._post_agent_msg(ch, executor_code, "처리 중 오류가 발생했습니다.", team_ch)
                return executor_code, ""

        async def _run_one(agent_code: str) -> tuple[str, str]:
            """단일 에이전트 작업 처리 — 위임 로직 포함"""
            # 미등록 에이전트 fallback
            if agent_code not in available:
                agent_code = "JX_CODER" if "JX_CODER" in available else next(iter(available), agent_code)

            persona = get_persona(agent_code)
            if not persona:
                return agent_code, ""
            home_channel = persona.channels[0] if persona.channels else channel

            # ── 위임 필요 여부 판단 ──
            executor_code = self._find_executor(agent_code, user_message)

            if executor_code and executor_code in available:
                # ── 수직 위임: 지시자 → 실행자 ──
                executor_persona = get_persona(executor_code)
                executor_home = executor_persona.channels[0] if executor_persona and executor_persona.channels else "dev"

                # 1. 지시자가 팀채널에서 위임 선언
                tracker.start_task(agent_code, f"작업 위임 → {get_korean_name(executor_code)}")
                delegation_msg = await _llm(
                    self._client, self._fast_model,
                    (
                        f"너는 {persona.role} {persona.korean_name}이다. 성격: {persona.personality}\n"
                        f"말투: {persona.speech_style}\n"
                        f"행동: 진수님이 준 작업을 직접 실행할 수 없어서 {get_korean_name(executor_code)}({executor_persona.role})에게 넘긴다.\n"
                        f"팀 채널에서 자연스럽게. 왜 넘기는지 + 어떤 방향으로 해달라는 요청. 2-3문장."
                    ),
                    f"진수님 지시: {user_message}\n\n{persona.korean_name}이 {get_korean_name(executor_code)}에게 어떻게 위임?",
                    max_tokens=300,
                )
                if delegation_msg:
                    await self._post_agent_msg(ch, agent_code, delegation_msg, home_channel, phase="delegate")
                tracker.complete_task(agent_code)
                await asyncio.sleep(0.8)

                # 2. 실행자가 위임 수락 + 계획 공유
                tracker.start_task(executor_code, user_message[:100])
                tracker.update_node(executor_code, GraphNode.PLAN)
                accept_msg = await _llm(
                    self._client, self._fast_model,
                    (
                        f"너는 {executor_persona.role} {executor_persona.korean_name}이다.\n"
                        f"성격: {executor_persona.personality}\n말투: {executor_persona.speech_style}\n"
                        f"행동: {persona.korean_name}({persona.role})로부터 작업을 넘겨받았다.\n"
                        f"팀원들한테 어떻게 진행할지 브리핑. 구체적으로. 2-3문장."
                    ),
                    f"원래 지시: {user_message}\n{persona.korean_name}의 요청: {delegation_msg or '작업 진행해줘'}\n\n{executor_persona.korean_name}이 팀에 브리핑:",
                    max_tokens=300,
                )
                if accept_msg:
                    await self._post_agent_msg(ch, executor_code, accept_msg, executor_home, phase="accept")
                await asyncio.sleep(0.5)

                # 3. 실행자가 실제 작업 수행
                full_instruction = await _build_instruction(user_message)
                code, output = await _run_executor(executor_code, full_instruction, executor_home)
                await asyncio.sleep(0.5)

                # 4. 실행자가 지시자에게 결과 보고 (팀채널)
                if output:
                    report_to_boss = await _llm(
                        self._client, self._fast_model,
                        (
                            f"너는 {executor_persona.role} {executor_persona.korean_name}이다.\n"
                            f"성격: {executor_persona.personality}\n말투: {executor_persona.speech_style}\n"
                            f"행동: {persona.korean_name}에게 작업 결과를 보고. 핵심만. 1-2문장."
                        ),
                        f"원래 지시: {user_message}\n작업 결과 요약: {output[:300]}\n\n{executor_persona.korean_name}이 {persona.korean_name}에게 보고:",
                        max_tokens=250,
                    )
                    if report_to_boss:
                        await self._post_agent_msg(ch, executor_code, report_to_boss, home_channel, phase="report")
                    await asyncio.sleep(0.5)

                    # 5. 지시자가 확인/피드백 (팀채널)
                    ack_msg = await _llm(
                        self._client, self._fast_model,
                        (
                            f"너는 {persona.role} {persona.korean_name}이다.\n"
                            f"성격: {persona.personality}\n말투: {persona.speech_style}\n"
                            f"행동: {get_korean_name(executor_code)}가 작업 완료 보고했다. 짧게 확인. 1문장."
                        ),
                        f"작업 결과: {report_to_boss or output[:200]}\n\n{persona.korean_name}의 확인:",
                        max_tokens=150,
                    )
                    if ack_msg:
                        await self._post_agent_msg(ch, agent_code, ack_msg, home_channel, phase="ack")

                return code, output

            else:
                # ── 직접 실행 가능한 에이전트 ──
                # 팀채널 브리핑
                tracker.start_task(agent_code, user_message[:100])
                tracker.update_node(agent_code, GraphNode.PLAN)
                brief = await _llm(
                    self._client, self._fast_model,
                    (
                        f"너는 {persona.role} {persona.korean_name}이다.\n"
                        f"성격: {persona.personality}\n말투: {persona.speech_style}\n"
                        "행동: 진수님 과제 받아서 팀원들에게 어떻게 처리할지 브리핑. 1-2문장."
                    ),
                    f"진수님 지시: {user_message}\n\n{persona.korean_name}이 팀에 브리핑:",
                    max_tokens=300,
                )
                if brief:
                    await self._post_agent_msg(ch, agent_code, brief, home_channel, phase="brief")

                # 실행
                full_instruction = await _build_instruction(user_message)
                return await _run_executor(agent_code, full_instruction, home_channel)

        try:
            # 모든 담당 에이전트 순차 실행 (위임 대화가 자연스럽게 이어지도록)
            results = []
            for a in agents:
                r = await _run_one(a)
                results.append(r)

            # 성공한 결과 수집
            outputs = [(code, out) for code, out in results if out]

            # 진수님 채널에 최종 결과 보고
            report_channel = channel if channel == "general" else "general"
            final_report = ""
            if outputs:
                core_persona = get_persona("JINXUS_CORE")
                parts = []
                for code, out in outputs:
                    p = get_persona(code)
                    excerpt = out[:400] + ("..." if len(out) > 400 else "")
                    parts.append(f"**{p.korean_name} ({p.role})**: {excerpt}")

                report_prompt = (
                    f"진수님 지시 내용: {user_message}\n\n"
                    f"팀 작업 결과:\n" + "\n\n".join(parts) + "\n\n"
                    "위 결과를 진수님께 CEO에게 보고하듯 간결하게 요약. "
                    "완료된 것, 주요 결과, 다음 행동 권고안 순서로. 존댓말 사용. 3-5문장."
                )
                final_report = await _llm(
                    self._client, self._fast_model,
                    "너는 JINXUS CEO 비서이자 오케스트레이터. 팀 작업 결과를 오너(진수님)께 보고한다.",
                    report_prompt,
                    max_tokens=400,
                )
                await self._post_agent_msg(ch, "JINXUS_CORE", final_report or "팀 작업이 완료됐습니다.", report_channel, is_result=True)

            # 업무 노트 자동 작성
            if outputs:
                await asyncio.to_thread(_write_work_note, user_message, agents, outputs)

            # 텔레그램 보고
            if outputs and telegram_callback:
                try:
                    agent_names = ", ".join(f"{get_korean_name(a)}({get_persona(a).role})" for a in agents)
                    report_text = (
                        f"✅ 업무 완료 보고\n\n"
                        f"📋 지시: {user_message[:80]}{'...' if len(user_message) > 80 else ''}\n"
                        f"👥 담당: {agent_names}\n\n"
                        f"📝 결과:\n{final_report or '완료됐습니다.'}\n\n"
                        f"📒 업무 노트 자동 작성됨"
                    )
                    await telegram_callback(report_text)
                except Exception as te:
                    logger.warning(f"[Reactor] 텔레그램 보고 실패: {te}")

        except Exception as e:
            logger.error(f"[Reactor] _execute_task 실패: {e}")
            try:
                await self._post_agent_msg(ch, "JINXUS_CORE", "작업 중 오류가 발생했습니다. 채팅 탭에서 다시 시도해 주세요.", channel)
            except Exception:
                logger.warning(f"채널 오류 알림 전송 실패")


# 싱글톤
_reactor: Optional[AgentReactor] = None


def get_agent_reactor() -> AgentReactor:
    global _reactor
    if _reactor is None:
        _reactor = AgentReactor()
    return _reactor
