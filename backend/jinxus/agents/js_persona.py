"""JS_PERSONA - 진수 전용 자소서/포트폴리오 에이전트

진수의 과거 자소서와 프로젝트 경험을 기억하고,
진수만의 어투와 스타일로 맞춤 자소서/포트폴리오를 작성한다.

JX_WRITER와 차이점:
- 일반 글쓰기 vs 진수 개인화 글쓰기
- JS_PERSONA는 진수의 과거 경험을 참조하여 더 진정성 있는 글 작성

v1.0: 초기 구현
"""
import asyncio
import uuid
import time
import logging
from datetime import datetime
from typing import Optional

from anthropic import Anthropic

from jinxus.config import get_settings
from jinxus.memory import get_jinx_memory
from jinxus.agents.state_tracker import get_state_tracker, GraphNode

logger = logging.getLogger(__name__)


class JSPersona:
    """진수 전용 글쓰기 에이전트

    블루프린트 그래프 구조:
    [receive] → [load_persona] → [plan] → [execute] → [evaluate] → [reflect] → [memory_write] → [return_result]
                                              ↑             │
                                              └──[retry]────┘  (최대 3회)
    """

    name = "JS_PERSONA"
    description = "진수 전용 자소서/포트폴리오 작성 에이전트"
    max_retries = 3

    # 회사 유형별 전략
    COMPANY_STRATEGIES = {
        "startup": {
            "keywords": ["스타트업", "startup", "초기", "시드", "시리즈A", "작은 팀"],
            "emphasis": ["자율성", "임팩트", "빠른 성장", "다양한 역할", "도전"],
            "tone": "열정적이고 도전적인",
        },
        "bigtech": {
            "keywords": ["네이버", "카카오", "라인", "쿠팡", "배민", "토스", "당근", "FAANG", "구글", "아마존", "메타"],
            "emphasis": ["확장성", "대규모 시스템", "협업", "기술적 깊이", "문제 해결"],
            "tone": "체계적이고 전문적인",
        },
        "enterprise": {
            "keywords": ["삼성", "LG", "SK", "현대", "대기업", "그룹사"],
            "emphasis": ["안정성", "조직 적응력", "장기 성장", "프로세스 개선", "리더십"],
            "tone": "신중하고 전문적인",
        },
        "research": {
            "keywords": ["연구소", "research", "AI 랩", "R&D", "박사", "논문"],
            "emphasis": ["연구 역량", "논문", "기술 탐구", "혁신", "학술적 기여"],
            "tone": "학술적이고 깊이 있는",
        },
        "default": {
            "keywords": [],
            "emphasis": ["열정", "성장", "학습", "문제 해결", "협업"],
            "tone": "진정성 있고 솔직한",
        },
    }

    # 진수 프로필 (기본값 - 장기기억에서 업데이트됨)
    JINSU_PROFILE = {
        "name": "진수",
        "field": "데이터 사이언스 / AI 엔지니어링",
        "strengths": [
            "복잡한 문제를 체계적으로 분석하고 해결",
            "새로운 기술 빠르게 학습하고 적용",
            "실용적인 AI 솔루션 개발",
            "효과적인 커뮤니케이션",
        ],
        "style": {
            "writing": "직접적이고 핵심만 전달",
            "personality": "문제 해결 지향적, 실용주의",
        },
    }

    def __init__(self):
        settings = get_settings()
        self._client = Anthropic(api_key=settings.anthropic_api_key)
        self._model = settings.claude_model
        self._memory = get_jinx_memory()
        self._prompt_version = "v1.0"
        self._persona_cache = None  # 진수 페르소나 캐시
        # 상태 추적기 (실시간 UI 연동)
        self._state_tracker = get_state_tracker()
        self._state_tracker.register_agent(self.name)

    def _get_system_prompt(self, company_strategy: dict, persona: dict) -> str:
        today = datetime.now().strftime("%Y년 %m월 %d일")

        strengths_str = "\n".join(f"- {s}" for s in persona.get("strengths", self.JINSU_PROFILE["strengths"]))
        emphasis_str = ", ".join(company_strategy["emphasis"])

        return f"""너는 JS_PERSONA야. 주인님(진수)의 자소서와 포트폴리오를 작성하는 전문가.

## 현재 날짜
오늘은 {today}이다.

## 핵심 역할
주인님의 과거 경험과 스타일을 반영하여 **진정성 있는** 자소서/포트폴리오를 작성한다.
일반적인 글쓰기가 아니라, "진수"라는 사람이 직접 쓴 것처럼 작성해야 한다.

## 주인님(진수) 프로필
- 분야: {persona.get("field", self.JINSU_PROFILE["field"])}
- 강점:
{strengths_str}
- 글쓰기 스타일: {persona.get("style", self.JINSU_PROFILE["style"])["writing"]}

## 이번 작성 전략 (회사 유형 기반)
- 강조할 키워드: {emphasis_str}
- 톤앤매너: {company_strategy["tone"]}

## 자소서 작성 원칙
1. **진정성**: 과장 없이 실제 경험 기반으로 작성
2. **구체성**: "열심히 했다" → "OO 기술로 처리 시간 30% 단축"
3. **차별화**: 왜 '진수'여야 하는지 보여주기
4. **스토리**: 경험의 맥락과 성장 과정 담기

## 금지 사항
- 뻔한 표현: "열정적입니다", "성실합니다", "팀워크가 좋습니다" (근거 없이)
- 추상적 서술: 구체적 수치나 결과 없는 주장
- 복붙 냄새: 어떤 회사에도 붙여넣기 가능한 글

## 말투
- 자소서 본문은 "~입니다", "~습니다" 체
- 주인님께 보고할 때는 "주인님"이라고 부른다
"""

    async def run(self, instruction: str, context: list = None) -> dict:
        """에이전트 실행 (전체 그래프 흐름)"""
        start_time = time.time()
        task_id = str(uuid.uuid4())

        try:
            # === [receive] 작업 시작 ===
            self._state_tracker.start_task(self.name, instruction)
            self._state_tracker.update_node(self.name, GraphNode.RECEIVE)

            # === [load_persona] 진수 페르소나 로드 ===
            persona = await self._load_persona()

            # === 회사 유형 파악 및 전략 결정 ===
            company_strategy = self._determine_company_strategy(instruction)

            # === 과거 자소서/포트폴리오 검색 ===
            memory_context = await self._search_past_writings(instruction)

            # === [plan] 작성 계획 ===
            self._state_tracker.update_node(self.name, GraphNode.PLAN)
            doc_type = self._determine_doc_type(instruction)
            plan = {
                "strategy": "write_persona_document",
                "doc_type": doc_type,
                "company_strategy": company_strategy,
                "instruction": instruction,
            }

            # === [execute] + [evaluate] + [retry] ===
            self._state_tracker.update_node(self.name, GraphNode.EXECUTE)
            result = await self._execute_with_retry(
                instruction, context, memory_context, persona, company_strategy, doc_type
            )

            # === [evaluate] ===
            self._state_tracker.update_node(self.name, GraphNode.EVALUATE)

            # === [reflect] 반성 ===
            self._state_tracker.update_node(self.name, GraphNode.REFLECT)
            reflection = await self._reflect(instruction, result)

            # === [memory_write] 장기기억 저장 ===
            self._state_tracker.update_node(self.name, GraphNode.MEMORY_WRITE)
            await self._memory_write(task_id, instruction, result, reflection)

            # === [return_result] ===
            self._state_tracker.update_node(self.name, GraphNode.RETURN_RESULT)
            duration_ms = int((time.time() - start_time) * 1000)

            return {
                "task_id": task_id,
                "agent_name": self.name,
                "success": result["success"],
                "success_score": result["score"],
                "output": result["output"],
                "failure_reason": result.get("error"),
                "duration_ms": duration_ms,
                "reflection": reflection,
            }

        except Exception as e:
            self._state_tracker.set_error(self.name, str(e))
            raise
        finally:
            self._state_tracker.complete_task(self.name)

    async def _load_persona(self) -> dict:
        """진수 페르소나 로드 (캐시 또는 메모리에서)"""
        if self._persona_cache:
            return self._persona_cache

        # 기본 프로필로 시작
        persona = dict(self.JINSU_PROFILE)
        persona["strengths"] = list(self.JINSU_PROFILE["strengths"])  # 복사
        extracted_strengths = set()
        extracted_experiences = []

        # 장기기억에서 진수 프로필 검색
        try:
            results = self._memory.search_long_term(
                agent_name=self.name,
                query="진수 프로필 강점 경력 성과",
                limit=10,
            )

            if results:
                for r in results:
                    summary = r.get("summary", "")
                    key_learnings = r.get("key_learnings", "")

                    # 강점 키워드 추출
                    extracted_strengths.update(
                        self._extract_strength_keywords(summary + " " + key_learnings)
                    )

                    # 경험/성과 추출
                    experience = self._extract_experience(summary)
                    if experience:
                        extracted_experiences.append(experience)

                # 추출된 강점을 프로필에 추가 (중복 제거)
                if extracted_strengths:
                    existing = set(persona["strengths"])
                    new_strengths = extracted_strengths - existing
                    persona["strengths"].extend(list(new_strengths)[:3])  # 최대 3개 추가

                # 최근 경험 저장
                if extracted_experiences:
                    persona["recent_experiences"] = extracted_experiences[:5]

                logger.info(f"Persona loaded: {len(extracted_strengths)} strengths, {len(extracted_experiences)} experiences")

            self._persona_cache = persona
            return persona

        except Exception as e:
            logger.warning(f"Persona load error: {e}")

        return self.JINSU_PROFILE

    def _extract_strength_keywords(self, text: str) -> set:
        """텍스트에서 강점 키워드 추출"""
        strength_patterns = [
            # 기술적 강점
            "데이터 분석", "머신러닝", "딥러닝", "AI", "Python",
            "문제 해결", "시스템 설계", "아키텍처", "최적화",
            "API 개발", "백엔드", "프론트엔드", "풀스택",
            # 소프트 스킬
            "커뮤니케이션", "협업", "리더십", "프로젝트 관리",
            "빠른 학습", "자기주도", "창의적", "분석적",
            # 성과 관련
            "성능 개선", "비용 절감", "자동화", "효율화",
        ]

        found = set()
        text_lower = text.lower()

        for pattern in strength_patterns:
            if pattern.lower() in text_lower:
                found.add(pattern)

        return found

    def _extract_experience(self, summary: str) -> Optional[str]:
        """요약에서 핵심 경험 추출"""
        # 성과/결과가 포함된 문장 찾기
        result_keywords = ["완료", "개선", "달성", "구현", "개발", "설계", "%", "절감"]

        for keyword in result_keywords:
            if keyword in summary:
                # 해당 키워드가 포함된 부분 추출 (최대 100자)
                idx = summary.find(keyword)
                start = max(0, idx - 50)
                end = min(len(summary), idx + 50)
                return summary[start:end].strip()

        return None

    def _determine_company_strategy(self, instruction: str) -> dict:
        """회사 유형 파악 및 전략 결정"""
        instruction_lower = instruction.lower()

        for strategy_name, strategy in self.COMPANY_STRATEGIES.items():
            if strategy_name == "default":
                continue
            for keyword in strategy["keywords"]:
                if keyword.lower() in instruction_lower:
                    logger.info(f"Company strategy detected: {strategy_name}")
                    return strategy

        return self.COMPANY_STRATEGIES["default"]

    def _determine_doc_type(self, instruction: str) -> str:
        """문서 유형 판단"""
        instruction_lower = instruction.lower()

        if any(kw in instruction_lower for kw in ["자소서", "자기소개서", "cover letter"]):
            return "cover_letter"
        elif any(kw in instruction_lower for kw in ["포트폴리오", "portfolio", "프로젝트 소개"]):
            return "portfolio"
        elif any(kw in instruction_lower for kw in ["이력서", "resume", "cv"]):
            return "resume"
        elif any(kw in instruction_lower for kw in ["면접", "interview", "질문"]):
            return "interview_prep"
        else:
            return "general"

    async def _search_past_writings(self, instruction: str) -> list:
        """과거 자소서/포트폴리오 검색"""
        try:
            # 1. JS_PERSONA의 과거 작업
            persona_results = self._memory.search_long_term(
                agent_name=self.name,
                query=instruction,
                limit=3,
            )

            # 2. JX_WRITER의 과거 자소서 작업
            writer_results = self._memory.search_long_term(
                agent_name="JX_WRITER",
                query="자소서 포트폴리오",
                limit=2,
            )

            return persona_results + writer_results

        except Exception as e:
            logger.warning(f"Past writings search error: {e}")
            return []

    async def _execute_with_retry(
        self,
        instruction: str,
        context: list,
        memory_context: list,
        persona: dict,
        company_strategy: dict,
        doc_type: str,
    ) -> dict:
        """실행 + 평가 + 재시도 (최대 3회, 지수 백오프)"""
        last_error = None

        for attempt in range(self.max_retries):
            try:
                result = await self._execute(
                    instruction, context, memory_context, persona, company_strategy, doc_type, last_error
                )

                if result["success"]:
                    return result

                last_error = result.get("error", "Unknown error")

                if attempt < self.max_retries - 1:
                    wait_time = 2 ** attempt
                    await asyncio.sleep(wait_time)

            except Exception as e:
                last_error = str(e)
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(2 ** attempt)

        return {
            "success": False,
            "score": 0.0,
            "output": f"죄송합니다 주인님, {self.max_retries}번 시도했지만 실패했습니다.\n마지막 오류: {last_error}",
            "error": last_error,
        }

    async def _execute(
        self,
        instruction: str,
        context: list,
        memory_context: list,
        persona: dict,
        company_strategy: dict,
        doc_type: str,
        last_error: str = None,
    ) -> dict:
        """단일 실행 시도"""

        # 과거 자소서 참고 문맥
        memory_str = ""
        if memory_context:
            memory_str = "\n\n## 참고: 과거 작성 경험\n"
            for m in memory_context[:3]:
                summary = m.get("summary", "")[:200]
                memory_str += f"- {summary}\n"

        # 에러 컨텍스트
        error_context = ""
        if last_error:
            error_context = f"\n\n이전 시도 오류: {last_error}\n이 오류를 피해서 다시 작성해줘."

        # 문서 유형별 추가 지시
        doc_type_guide = self._get_doc_type_guide(doc_type)

        prompt = f"""## 주인님의 요청
{instruction}
{memory_str}
{error_context}

## 문서 유형 가이드
{doc_type_guide}

주인님의 경험과 스타일을 반영하여 작성해줘.
"""

        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=4096,
                system=self._get_system_prompt(company_strategy, persona),
                messages=[{"role": "user", "content": prompt}],
            )

            output = response.content[0].text

            return {
                "success": True,
                "score": 0.95,
                "output": f"주인님, 작성이 완료되었습니다.\n\n{output}",
                "error": None,
            }

        except Exception as e:
            logger.error(f"Execute error: {e}")
            return {
                "success": False,
                "score": 0.0,
                "output": f"작업 실행 중 오류: {str(e)[:200]}",
                "error": str(e),
            }

    def _get_doc_type_guide(self, doc_type: str) -> str:
        """문서 유형별 가이드"""
        guides = {
            "cover_letter": """
자소서 작성 가이드:
1. 지원 동기: 왜 이 회사/직무인지 (진정성 있게)
2. 강점: 직무 관련 구체적 경험과 성과
3. 성장 가능성: 어떻게 기여할 것인지
4. 분량: 항목당 300-500자
""",
            "portfolio": """
포트폴리오 작성 가이드:
1. 프로젝트명 + 한 줄 요약
2. 문제 정의: 무슨 문제를 해결했나
3. 기술 스택 및 역할
4. 결과 및 임팩트 (수치로)
5. 배운 점
""",
            "resume": """
이력서 작성 가이드:
1. 핵심 역량 3가지 (한 줄씩)
2. 경력/프로젝트: 성과 중심
3. 기술 스택: 숙련도 명시
""",
            "interview_prep": """
면접 준비 가이드:
1. 예상 질문 + 답변 프레임
2. STAR 기법 적용 (상황-과제-행동-결과)
3. 꼬리 질문 대비
""",
        }
        return guides.get(doc_type, "일반 문서 작성: 명확하고 간결하게")

    async def _reflect(self, instruction: str, result: dict) -> str:
        """반성: 이번 작업에서 배운 점"""
        if not result["success"]:
            return f"실패 원인: {result.get('error', 'Unknown')}. 다음에는 이 패턴을 피해야 함."

        try:
            reflect_prompt = f"""방금 완료한 자소서/포트폴리오 작성:
요청: {instruction[:200]}
결과: 성공

이 작업에서 배운 점을 1-2문장으로 정리해줘. 특히 회사 유형이나 직무에 맞춘 전략이 있었다면 기록해."""

            response = self._client.messages.create(
                model=self._model,
                max_tokens=256,
                messages=[{"role": "user", "content": reflect_prompt}],
            )
            return response.content[0].text

        except Exception:
            return "작업 성공. 추가 반성 없음."

    async def _memory_write(
        self, task_id: str, instruction: str, result: dict, reflection: str
    ) -> None:
        """장기기억에 저장"""
        try:
            # 자소서 작업은 항상 저장 (진수 패턴 학습용)
            importance = 0.7
            if not result["success"]:
                importance += 0.2

            self._memory.save_long_term(
                agent_name=self.name,
                task_id=task_id,
                instruction=instruction,
                summary=result["output"][:500],
                outcome="success" if result["success"] else "failure",
                success_score=result["score"],
                key_learnings=reflection,
                importance_score=importance,
                prompt_version=self._prompt_version,
            )

        except Exception as e:
            logger.warning(f"Memory write error: {e}")

    async def update_persona(self, profile_updates: dict) -> bool:
        """진수 프로필 업데이트

        Args:
            profile_updates: {"strengths": [...], "field": "...", ...}

        Returns:
            성공 여부
        """
        try:
            # 캐시 업데이트
            if self._persona_cache is None:
                self._persona_cache = dict(self.JINSU_PROFILE)

            for key, value in profile_updates.items():
                self._persona_cache[key] = value

            # 장기기억에 프로필 저장
            self._memory.save_long_term(
                agent_name=self.name,
                task_id=str(uuid.uuid4()),
                instruction="프로필 업데이트",
                summary=f"진수 프로필 업데이트: {profile_updates}",
                outcome="success",
                success_score=1.0,
                key_learnings="프로필 업데이트됨",
                importance_score=0.9,
                prompt_version=self._prompt_version,
            )

            logger.info(f"Persona updated: {profile_updates}")
            return True

        except Exception as e:
            logger.error(f"Persona update error: {e}")
            return False
