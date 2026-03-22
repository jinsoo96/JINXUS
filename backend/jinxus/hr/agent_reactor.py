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
                msg_type = "question"
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
            matrix_as = self._get_matrix_as()
            prev_reactions: List[tuple[str, str]] = []  # (agent_code, reaction)
            for agent in agents:
                reaction = await self._generate_reaction(
                    agent, user_message, msg_type, reason, prev_reactions, recent_history
                )
                if not reaction:
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
                    max_tokens=150,
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
                        max_tokens=100,
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
                        max_tokens=80,
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

        return await _llm(self._client, self._fast_model, system, prompt, max_tokens=180)

    async def _execute_task(self, user_message: str, agents: List[str], channel: str, history: Optional[List[dict]] = None, telegram_callback=None):
        """실제 작업 실행 — 분류된 에이전트들이 병렬로 직접 처리

        JINXUS_CORE를 거치지 않고, 각 에이전트가 담당 작업을 직접 실행한다.
        결과는 각 에이전트의 소속 채널(+ 원래 채널)에 게시한다.
        모든 에이전트 완료 후 JINXUS_CORE가 최종 요약을 원래 채널에 게시한다.
        """
        from jinxus.agents import get_agent, register_all_agents

        ch = get_company_channel()

        # 채널 기반 fallback 라우팅: 등록된 에이전트가 없을 때 채널별 기본 에이전트 사용
        _CHANNEL_FALLBACK = {
            "engineering": "JX_CODER",
            "research":    "JX_RESEARCHER",
            "marketing":   "JX_MARKETING",
            "ops":         "JX_OPS",
            "planning":    "JX_ANALYST",
        }
        # 키워드 기반 fallback
        _KEYWORD_FALLBACK = [
            (["코드", "개발", "구현", "만들어", "작성", "버그", "수정", "파일", "함수", "클래스"], "JX_CODER"),
            (["조사", "리서치", "검색", "찾아", "분석", "정보"], "JX_RESEARCHER"),
            (["마케팅", "캠페인", "sns", "광고"], "JX_MARKETING"),
            (["운영", "서버", "배포", "인프라"], "JX_OPS"),
            (["전략", "기획", "계획", "분석"], "JX_ANALYST"),
        ]
        available = set(register_all_agents().keys())

        def _resolve_agent(code: str) -> str:
            """실제 실행 가능한 에이전트 코드 반환. 미등록이면 fallback."""
            if code in available:
                return code
            # 채널 기반 fallback
            fb = _CHANNEL_FALLBACK.get(channel)
            if fb and fb in available:
                return fb
            # 키워드 기반 fallback
            lower = user_message.lower()
            for keywords, fb_code in _KEYWORD_FALLBACK:
                if any(k in lower for k in keywords) and fb_code in available:
                    return fb_code
            return "JX_CODER" if "JX_CODER" in available else next(iter(available), code)

        async def _run_one(agent_code: str) -> tuple[str, str]:
            """단일 에이전트 실행 → (agent_code, output) 반환"""
            resolved = _resolve_agent(agent_code)
            if resolved != agent_code:
                logger.info(f"[Reactor] {agent_code} 미등록 → {resolved} fallback")
                agent_code = resolved

            persona = get_persona(agent_code)
            agent = get_agent(agent_code)

            if not agent:
                logger.warning(f"[Reactor] 에이전트 인스턴스 없음: {agent_code}")
                return agent_code, ""

            # 팀 소속 채널에서 내부 시작 브리핑 (팀장이 팀원들에게)
            home_channel = persona.channels[0] if persona.channels else channel
            brief = await _llm(
                self._client, self._fast_model,
                (
                    f"너는 JINXUS 팀의 {persona.role} {persona.korean_name}이다.\n"
                    f"성격: {persona.personality}\n말투: {persona.speech_style}\n"
                    "행동 규칙: 진수님이 준 과제를 받아서 팀원들에게 내부적으로 어떻게 처리할지 짧게 브리핑. "
                    "팀원 이름 언급 가능. 직장인처럼 자연스럽게. 1-2문장."
                ),
                f"진수님 지시: {user_message}\n\n{persona.korean_name}이 팀 채널에 어떻게 브리핑?",
                max_tokens=120,
            )
            if brief:
                await ch.post(
                    from_name=persona.full_name,
                    content=brief,
                    channel=home_channel,
                    message_type="chat",
                    metadata={"agent_code": agent_code, "phase": "brief"},
                )

            try:
                # 히스토리 맥락 포함 — 모호한 지시도 이전 대화에서 의도 파악
                history_text = ""
                if history:
                    lines = []
                    for h in history[-8:]:
                        speaker = h.get("from_name", h.get("role", "?"))
                        content = h.get("content", "")[:200]
                        lines.append(f"{speaker}: {content}")
                    history_text = "\n".join(lines)

                full_instruction = user_message
                if history_text:
                    full_instruction = (
                        f"[최근 대화 맥락]\n{history_text}\n\n"
                        f"[진수님 지시]\n{user_message}\n\n"
                        f"[행동 규칙] 위 맥락을 참고해서 가장 합리적인 작업을 즉시 시작. "
                        f"추가 설명 요청 금지. 뭘 할지 모르겠으면 맥락에서 가장 최근에 논의된 것을 실행."
                    )

                result = await agent.run(
                    instruction=full_instruction,
                    context=[{"role": "user", "content": full_instruction}],
                )
                output = result.get("output", "") or result.get("response", "")
                if output:
                    # 팀 채널에 중간 결과 공유
                    summary = output[:500] + ("..." if len(output) > 500 else "")
                    await ch.post(
                        from_name=persona.full_name,
                        content=summary,
                        channel=home_channel,
                        message_type="chat",
                        metadata={"agent_code": agent_code, "is_result": True},
                    )
                return agent_code, output
            except Exception as e:
                logger.error(f"[Reactor] {agent_code} 실행 실패: {e}")
                await ch.post(
                    from_name=persona.full_name,
                    content="처리 중 오류가 발생했습니다.",
                    channel=home_channel,
                    message_type="system",
                    metadata={"agent_code": agent_code},
                )
                return agent_code, ""

        try:
            # 모든 담당 에이전트 병렬 실행
            results = await asyncio.gather(
                *[_run_one(a) for a in agents],
                return_exceptions=True,
            )

            # 성공한 결과 수집
            outputs = [
                (code, out)
                for r in results
                if not isinstance(r, Exception)
                for code, out in [r]
                if out
            ]

            # 진수님이 있는 채널에 최종 결과 보고 — 항상 general 또는 원래 채널
            report_channel = "general" if channel != "general" else channel
            final_report = ""
            if outputs:
                core_persona = get_persona("JINXUS_CORE")
                # 각 팀장 보고 내용 취합
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
                    max_tokens=300,
                )
                await ch.post(
                    from_name=core_persona.full_name,
                    content=final_report or "팀 작업이 완료됐습니다.",
                    channel=report_channel,
                    message_type="chat",
                    metadata={"agent_code": "JINXUS_CORE", "is_result": True},
                )

            # 업무 노트 자동 작성 (asyncio 블로킹 방지)
            if outputs:
                await asyncio.to_thread(
                    _write_work_note, user_message, agents, outputs
                )

            # 텔레그램 보고 (콜백이 있으면)
            if outputs and telegram_callback:
                try:
                    agent_names = ", ".join(
                        f"{get_korean_name(a)}({get_persona(a).role})"
                        for a in agents
                    )
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
                core_persona = get_persona("JINXUS_CORE")
                await ch.post(
                    from_name=core_persona.full_name,
                    content="작업 중 오류가 발생했습니다. 채팅 탭에서 다시 시도해 주세요.",
                    channel=channel,
                    message_type="system",
                )
            except Exception as e:
                logger.warning(f"채널 오류 알림 전송 실패: {e}")


# 싱글톤
_reactor: Optional[AgentReactor] = None


def get_agent_reactor() -> AgentReactor:
    global _reactor
    if _reactor is None:
        _reactor = AgentReactor()
    return _reactor
