"""Dynamic Tool Executor - Claude tool_use 기반 자동 도구 선택 및 실행

에이전트가 작업 지시를 받으면:
1. 사용 가능한 도구 목록을 Claude에게 제공
2. Claude가 적절한 도구 선택 및 인자 결정
3. 선택된 도구 실행
4. 결과 반환

MCP 도구 포함 모든 도구를 자동으로 활용 가능.
"""
import asyncio
import json
import logging
import re
import threading
import time as _time
from typing import Optional, Callable
from dataclasses import dataclass, field

from anthropic import Anthropic

from jinxus.config import get_settings
from .base import JinxTool

logger = logging.getLogger(__name__)

# Guard-Post 완료 시그널 패턴 (Geny 패턴 참고)
_COMPLETION_PATTERNS = [
    (re.compile(r'\[TASK_COMPLETE\]', re.IGNORECASE), 'complete'),
    (re.compile(r'\[BLOCKED:\s*(.+?)\]', re.IGNORECASE), 'blocked'),
    (re.compile(r'\[ERROR:\s*(.+?)\]', re.IGNORECASE), 'error'),
]

# 컨텍스트 압축 임계값 (대략 80k 토큰 = 240k 글자)
_CTX_COMPRESS_THRESHOLD_CHARS = 240_000


@dataclass
class ToolCall:
    """도구 호출 정보"""
    tool_name: str
    arguments: dict
    tool_use_id: str


@dataclass
class ExecutionResult:
    """실행 결과"""
    success: bool
    output: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    raw_results: list[dict] = field(default_factory=list)
    error: Optional[str] = None


class DynamicToolExecutor:
    """Claude tool_use 기반 동적 도구 실행기

    사용 예:
        executor = DynamicToolExecutor(agent_name="JX_RESEARCHER")
        result = await executor.execute(
            instruction="최신 AI 트렌드 검색해줘",
            system_prompt="너는 리서치 전문가야..."
        )
    """

    # 도구 카테고리별 가이드라인 (Progressive Disclosure: 보유 도구만 주입)
    _GUIDE_SECTIONS = {
        "weather": """### 날씨 조회
- 날씨/기온/강수확률: `weather` 도구 사용 (OpenWeatherMap, 서울 구별 지원)
- weather 실패 시: `naver_searcher`로 폴백""",

        "naver_searcher": """### 한국어 검색
- 한국어 검색 (뉴스, 로컬 정보): `naver_searcher` 도구 사용""",

        "web_searcher": """### 웹 검색
- 영문/글로벌 검색: `web_searcher` (Tavily) 또는 `mcp__brave_search__*`""",

        "mcp:fetch": """### 웹 페이지 가져오기
- 웹페이지 내용 가져오기: `mcp__fetch__*` 도구 사용""",

        "mcp:playwright": """### 브라우저 자동화
- 브라우저 자동화: `mcp__playwright__*` 도구 사용""",

        "github_agent": """### GitHub 관련 작업
- GitHub 레포지토리/커밋/PR/이슈 조회: **`github_agent` 도구 사용** (action 파라미터로 작업 지정)
  - 커밋 목록: action="list_commits", repo="owner/repo" 또는 username="사용자명"
  - 레포 목록: action="list_user_repos", username="사용자명"
  - 레포 검색: action="search_repos", query="검색어"
  - 레포 정보: action="get_repo", repo="owner/repo"
- `mcp__github__*` 도구는 deprecated → **사용 금지**. 반드시 `github_agent` 사용
- **절대로** `mcp__filesystem__*` 도구로 GitHub 작업하지 마라 (권한 오류 발생)""",

        "mcp:filesystem": """### 파일 시스템 작업
- 로컬 파일 읽기/쓰기: `mcp__filesystem__*` 도구 사용
- 단, 허용된 경로만 접근 가능 (/ 루트 접근 불가)
- **절대로 URL(http://, https://)을 `mcp__filesystem__*` 도구에 전달하지 마라. URL은 파일 경로가 아니다.**""",

        "mcp:git": """### Git 작업
- git commit, push, branch: `mcp__git__*` 도구 사용""",

        "mcp:firecrawl": """### 웹 크롤링/스크래핑
- 웹사이트 전체 크롤링: `mcp__firecrawl__*` 도구 사용
- 자소서/채용공고/블로그 등 JS 렌더링 필요한 사이트 크롤링에 적합
- 단일 페이지 추출은 `mcp__fetch__*`, 사이트 전체는 `mcp__firecrawl__*`""",

        "data_processor": """### 데이터 분석
- CSV/Excel/JSON 파일 분석: `data_processor` 도구 사용
  - read: 파일 내용 조회
  - describe: 통계 요약 (평균, 중앙값, 분포)
  - filter: 조건 필터링 (예: 'age > 30')
  - convert: 포맷 변환 (CSV↔Excel↔JSON)""",

        "doc_generator": """### 문서 생성
- Word 문서(.docx) 생성: `doc_generator` 도구 사용 (format="docx")
- PowerPoint(.pptx) 생성: `doc_generator` 도구 사용 (format="pptx")
- 마크다운 형식으로 content 전달 → 자동 변환""",

        "mcp:notion": """### Notion 연동
- Notion 페이지/데이터베이스 조회·생성·수정: `mcp__notion__*` 도구 사용""",

        "mcp:sqlite": """### SQLite 쿼리
- SQLite DB 쿼리 실행: `mcp__sqlite__*` 도구 사용""",

        "stock_price": """### 주식/암호화폐 시세
- 주가, 코인 가격 조회: `stock_price` 도구 사용 (Yahoo Finance + CoinGecko)""",

        "rss_reader": """### RSS/뉴스 피드
- RSS 피드 구독: `rss_reader` 도구 사용
- 내장 피드: hn(HackerNews), techcrunch, naver_it, ednet 등""",

        "image_analyzer": """### 이미지 분석
- 이미지 분석/OCR/차트 해석: `image_analyzer` 도구 사용 (Claude Vision)""",

        "pdf_reader": """### PDF 분석
- PDF 텍스트 추출: `pdf_reader` 도구 사용 (페이지 범위 지정 가능)""",
    }

    _GUIDE_COMMON = """
### 도구 선택 원칙
1. 작업 목적에 맞는 도구 선택
2. 에러 발생 시 다른 도구로 폴백 시도
3. 확실하지 않으면 먼저 목록 조회 도구 사용 (list_*, get_* 등)
4. 반드시 도구를 호출해서 정보를 가져와라. 도구 없이 지어내기 금지.

### 핵심 금지 사항
- URL(http://, https://)이 포함된 경로를 `mcp__filesystem__*` 도구에 절대 전달 금지
- GitHub 레포 내용 읽기 → `github_agent` 또는 `github_graphql` 또는 `mcp__fetch__*` 사용. `mcp__filesystem__*` 사용 금지.
"""

    def __init__(
        self,
        agent_name: str,
        max_tool_rounds: int = 15,
        model: Optional[str] = None,
    ):
        """
        Args:
            agent_name: 에이전트 이름 (도구 필터링용)
            max_tool_rounds: 최대 도구 호출 라운드 수
            model: 사용할 모델 (기본: settings.claude_model)
        """
        settings = get_settings()
        self._client = Anthropic(api_key=settings.anthropic_api_key)
        self._model = model or settings.claude_model
        self._agent_name = agent_name
        # Tool Policy Engine에서 에이전트별 max_rounds / continuations 가져오기
        from jinxus.core.tool_policy import get_max_tool_rounds, get_max_continuations
        self._max_rounds = max_tool_rounds if max_tool_rounds != 15 else get_max_tool_rounds(agent_name, default=15)
        self._max_continuations = get_max_continuations(agent_name, default=2)
        self._tools_cache: Optional[dict[str, JinxTool]] = None
        self._schemas_cache: Optional[list[dict]] = None
        # 시스템 프롬프트 캐시 (최대 8개, LRU 방식)
        self._enhanced_system_prompt_cache: dict[str, str] = {}
        self._PROMPT_CACHE_MAX = 8

    def _get_available_tools(self) -> dict[str, JinxTool]:
        """에이전트가 사용 가능한 도구 로드 (Tool Policy Engine 적용, 캐시)"""
        if self._tools_cache is not None:
            return self._tools_cache
        from . import get_tools_for_agent
        from jinxus.core.tool_policy import filter_tools_for_agent
        raw_tools = get_tools_for_agent(self._agent_name)
        self._tools_cache = filter_tools_for_agent(self._agent_name, raw_tools)
        return self._tools_cache

    def _sanitize_tool_name(self, name: str) -> str:
        """도구 이름을 Claude API 호환 형식으로 변환

        mcp:playwright:browser_click -> mcp__playwright__browser_click
        """
        return name.replace(":", "__")

    def _restore_tool_name(self, sanitized_name: str) -> str:
        """Claude API 형식 이름을 원래 형식으로 복원

        mcp__playwright__browser_click -> mcp:playwright:browser_click
        """
        return sanitized_name.replace("__", ":")

    def _build_tool_guide(self) -> str:
        """보유 도구에 맞는 가이드라인만 동적 생성 (Progressive Disclosure)"""
        tools = self._get_available_tools()
        tool_names = set(tools.keys())

        sections = []
        for key, guide_text in self._GUIDE_SECTIONS.items():
            # 정확 매치 또는 prefix 매치 (mcp:fetch → mcp:fetch:*)
            if key in tool_names or any(t.startswith(key) for t in tool_names):
                sections.append(guide_text)

        if not sections:
            return self._GUIDE_COMMON

        return "\n## 도구 선택 가이드라인 (중요!)\n\n" + "\n\n".join(sections) + "\n" + self._GUIDE_COMMON

    def _build_tool_schemas(self) -> list[dict]:
        """Claude tool_use 형식으로 도구 스키마 생성"""
        tools = self._get_available_tools()
        schemas = []

        for name, tool in tools.items():
            # JinxTool의 input_schema 가져오기
            input_schema = getattr(tool, 'input_schema', None)

            if input_schema is None:
                # 기본 스키마: 단일 input 파라미터
                input_schema = {
                    "type": "object",
                    "properties": {
                        "input": {
                            "type": "string",
                            "description": "도구 입력값"
                        }
                    },
                    "required": ["input"]
                }

            # Claude API는 도구 이름에 콜론(:) 불가 -> 언더스코어로 변환
            sanitized_name = self._sanitize_tool_name(name)

            schemas.append({
                "name": sanitized_name,
                "description": tool.description or f"{name} 도구",
                "input_schema": input_schema,
            })

        return schemas

    async def execute(
        self,
        instruction: str,
        system_prompt: str,
        context: Optional[str] = None,
        initial_messages: Optional[list[dict]] = None,
        tool_callback: Optional[Callable] = None,
    ) -> ExecutionResult:
        """작업 실행 - Claude가 필요한 도구 자동 선택 및 실행

        Args:
            instruction: 수행할 작업 지시
            system_prompt: 시스템 프롬프트
            context: 추가 컨텍스트 (이전 작업 결과 등)
            initial_messages: 초기 대화 히스토리

        Returns:
            ExecutionResult: 실행 결과
        """
        tools = self._get_available_tools()
        # 스키마 캐시: 도구 목록은 실행 중 변하지 않으므로 한 번만 빌드
        if self._schemas_cache is None:
            self._schemas_cache = self._build_tool_schemas()
        tool_schemas = self._schemas_cache

        # 시스템 프롬프트 + 도구 가이드 캐시 (보유 도구 기반 동적 생성, 최대 _PROMPT_CACHE_MAX개)
        if system_prompt not in self._enhanced_system_prompt_cache:
            if len(self._enhanced_system_prompt_cache) >= self._PROMPT_CACHE_MAX:
                # 가장 오래된 항목 제거 (dict는 삽입 순서 유지)
                oldest_key = next(iter(self._enhanced_system_prompt_cache))
                del self._enhanced_system_prompt_cache[oldest_key]
            self._enhanced_system_prompt_cache[system_prompt] = system_prompt + self._build_tool_guide()
        enhanced_system_prompt = self._enhanced_system_prompt_cache[system_prompt]

        # 도구가 없으면 일반 대화
        if not tool_schemas:
            response = await asyncio.to_thread(self._client.messages.create,
                model=self._model,
                max_tokens=4096,
                system=system_prompt,
                messages=[{"role": "user", "content": instruction}],
            )
            return ExecutionResult(
                success=True,
                output=response.content[0].text,
                tool_calls=[],
                raw_results=[],
            )

        # 메시지 구성
        messages = initial_messages or []
        user_content = instruction
        if context:
            user_content = f"{instruction}\n\n## 참고 컨텍스트\n{context}"
        messages.append({"role": "user", "content": user_content})

        all_tool_calls = []
        all_raw_results = []

        # Continuation 루프: max_rounds 도달 후에도 작업이 미완료면 이어하기
        for continuation in range(self._max_continuations + 1):
            if continuation > 0:
                logger.info(
                    f"[{self._agent_name}] Continuation {continuation}/{self._max_continuations} 시작 "
                    f"(누적 도구 호출: {len(all_tool_calls)}개)"
                )

            result = await self._execute_rounds(
                messages=messages,
                enhanced_system_prompt=enhanced_system_prompt,
                tool_schemas=tool_schemas,
                all_tool_calls=all_tool_calls,
                all_raw_results=all_raw_results,
                tool_callback=tool_callback,
            )

            # 정상 완료 (도구 호출 없이 텍스트 응답으로 종료)
            if result is not None:
                return result

            # max_rounds 도달 → continuation 가능 여부 확인
            if continuation >= self._max_continuations:
                break

            # 지금까지 결과 요약하여 새 세션으로 이어하기
            summary = self._build_continuation_summary(all_tool_calls, all_raw_results)
            messages = [
                {"role": "user", "content": (
                    f"## 이전 작업 이어하기 (continuation {continuation + 1})\n\n"
                    f"**원래 지시:** {instruction}\n\n"
                    f"**지금까지 완료된 작업:**\n{summary}\n\n"
                    f"위 결과를 바탕으로 남은 작업을 이어서 완료하라. "
                    f"이미 수행한 작업은 반복하지 말고, 미완료 부분만 처리하라."
                )},
            ]

            if tool_callback:
                try:
                    await tool_callback("_continuation", "calling")
                except Exception as e:
                    logger.warning(f"[DynamicToolExecutor] continuation 콜백 호출 실패: {e}")

        # 모든 continuation 소진
        logger.warning(
            f"[{self._agent_name}] 최대 도구 라운드 + continuation {self._max_continuations}회 모두 도달 "
            f"(총 도구 호출: {len(all_tool_calls)}개)"
        )

        # 마지막에 요약 응답 생성 요청
        final_messages = [
            {"role": "user", "content": (
                f"도구 호출 한도에 도달했다. 지금까지 수행한 작업을 바탕으로 최종 결과를 정리하여 응답하라.\n\n"
                f"**원래 지시:** {instruction}\n\n"
                f"**수행한 도구 호출 ({len(all_tool_calls)}건):**\n"
                + self._build_continuation_summary(all_tool_calls, all_raw_results)
            )},
        ]
        try:
            response = await asyncio.to_thread(self._client.messages.create,
                model=self._model,
                max_tokens=4096,
                system=enhanced_system_prompt,
                messages=final_messages,
            )
            final_text = ""
            for block in response.content:
                if block.type == "text":
                    final_text = block.text
            if final_text:
                return ExecutionResult(
                    success=True,
                    output=final_text,
                    tool_calls=all_tool_calls,
                    raw_results=all_raw_results,
                )
        except Exception as e:
            logger.error(f"[{self._agent_name}] 최종 요약 생성 실패: {e}")

        return ExecutionResult(
            success=True,
            output="도구 호출 최대 횟수에 도달했습니다. 부분 결과가 포함되어 있습니다.",
            tool_calls=all_tool_calls,
            raw_results=all_raw_results,
        )

    def _build_continuation_summary(
        self,
        tool_calls: list[ToolCall],
        raw_results: list[dict],
    ) -> str:
        """도구 호출 결과를 요약하여 continuation 컨텍스트 생성"""
        lines = []
        for i, (tc, result) in enumerate(zip(tool_calls, raw_results)):
            original_name = self._restore_tool_name(tc.tool_name)
            success = result.get("success", False)
            status = "성공" if success else "실패"
            output = str(result.get("output") or result.get("error", ""))
            # 결과가 너무 길면 요약
            if len(output) > 500:
                output = output[:500] + f"... (총 {len(output)}자)"
            lines.append(f"{i+1}. [{status}] {original_name} → {output}")
        return "\n".join(lines) if lines else "(없음)"

    async def _execute_rounds(
        self,
        messages: list[dict],
        enhanced_system_prompt: str,
        tool_schemas: list[dict],
        all_tool_calls: list[ToolCall],
        all_raw_results: list[dict],
        tool_callback: Optional[Callable] = None,
    ) -> Optional[ExecutionResult]:
        """도구 호출 라운드 실행. 정상 완료 시 ExecutionResult 반환, max_rounds 도달 시 None 반환."""
        for round_num in range(self._max_rounds):
            _round_start = _time.time()
            msg_count = len(messages)
            logger.debug(f"[{self._agent_name}] round={round_num} messages={msg_count} model={self._model} tools={len(tool_schemas)}")

            response = await asyncio.to_thread(self._client.messages.create,
                model=self._model,
                max_tokens=4096,
                system=enhanced_system_prompt,
                messages=messages,
                tools=tool_schemas,
            )
            _api_ms = (_time.time() - _round_start) * 1000
            logger.debug(f"[{self._agent_name}] Claude API 응답 {_api_ms:.0f}ms usage=({response.usage.input_tokens}in/{response.usage.output_tokens}out) stop={response.stop_reason}")

            # 응답 처리
            assistant_content = []
            tool_uses = []
            final_text = ""

            for block in response.content:
                if block.type == "text":
                    final_text = block.text
                    assistant_content.append({"type": "text", "text": block.text})
                elif block.type == "tool_use":
                    tool_uses.append(block)
                    assistant_content.append({
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                    })

            # 도구 호출이 없으면 완료
            if not tool_uses:
                # Guard-Post 완료 시그널 감지
                for pattern, signal_type in _COMPLETION_PATTERNS:
                    m = pattern.search(final_text)
                    if m:
                        clean_text = pattern.sub('', final_text).strip()
                        if signal_type == 'complete':
                            logger.info(f"[{self._agent_name}] 완료 시그널 [TASK_COMPLETE] 감지")
                            return ExecutionResult(
                                success=True,
                                output=clean_text or final_text,
                                tool_calls=all_tool_calls,
                                raw_results=all_raw_results,
                            )
                        elif signal_type in ('blocked', 'error'):
                            reason = m.group(1) if m.lastindex else signal_type
                            logger.warning(f"[{self._agent_name}] 차단 시그널 [{signal_type.upper()}] 감지: {reason}")
                            return ExecutionResult(
                                success=False,
                                output=clean_text or final_text,
                                tool_calls=all_tool_calls,
                                raw_results=all_raw_results,
                                error=f"{signal_type.upper()}: {reason}",
                            )

                logger.debug(f"[{self._agent_name}] 도구 호출 없음, 텍스트 응답 {len(final_text)}자 반환")
                return ExecutionResult(
                    success=True,
                    output=final_text,
                    tool_calls=all_tool_calls,
                    raw_results=all_raw_results,
                )

            # 메시지에 assistant 응답 추가
            messages.append({"role": "assistant", "content": assistant_content})

            # 도구 실행
            tool_results = []
            for tool_use in tool_uses:
                tool_name = tool_use.name
                tool_input = tool_use.input
                tool_id = tool_use.id

                call = ToolCall(
                    tool_name=tool_name,
                    arguments=tool_input,
                    tool_use_id=tool_id,
                )
                all_tool_calls.append(call)

                # 원래 이름으로 로깅
                original_tool_name = self._restore_tool_name(tool_name)

                # 도구 입력 요약 (긴 값은 잘라서)
                input_summary = {k: (str(v)[:80] + "..." if len(str(v)) > 80 else v) for k, v in tool_input.items()}
                logger.info(f"[{self._agent_name}] TOOL_CALL {original_tool_name}({input_summary})")

                # 도구 호출 시작 콜백
                if tool_callback:
                    try:
                        await tool_callback(original_tool_name, "calling")
                    except Exception as e:
                        logger.warning(f"[DynamicToolExecutor] 도구 시작 콜백 실패 ({original_tool_name}): {e}")

                # 실제 도구 실행 (메트릭 포함)
                _tool_start = _time.time()
                result = await self._execute_tool(tool_name, tool_input)
                _tool_duration = (_time.time() - _tool_start) * 1000
                all_raw_results.append(result)

                success = result.get("success", False)
                result_preview = str(result.get("output") or result.get("error", ""))[:150]
                logger.info(f"[{self._agent_name}] TOOL_RESULT {original_tool_name} {'OK' if success else 'FAIL'} {_tool_duration:.0f}ms | {result_preview}")

                # 도구 실행 메트릭 기록
                try:
                    from jinxus.core.metrics import get_metrics
                    get_metrics().record_tool_execution(original_tool_name, _tool_duration, success)
                except Exception as e:
                    logger.warning(f"[DynamicToolExecutor] 메트릭 기록 실패 ({original_tool_name}): {e}")

                # 도구 호출 로그 기록 (실시간 UI용)
                try:
                    from jinxus.agents.state_tracker import get_state_tracker
                    get_state_tracker().log_tool_call(
                        agent_name=self._agent_name,
                        tool_name=original_tool_name,
                        status="success" if success else "error",
                        duration_ms=_tool_duration,
                        error=result.get("error") if not success else None,
                    )
                except Exception as e:
                    logger.warning(f"[DynamicToolExecutor] 도구 호출 로그 기록 실패 ({original_tool_name}): {e}")

                # 도구 호출 완료 콜백
                if tool_callback:
                    try:
                        await tool_callback(original_tool_name, "done" if success else "error")
                    except Exception as e:
                        logger.warning(f"[DynamicToolExecutor] 도구 완료 콜백 실패 ({original_tool_name}): {e}")

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tool_id,
                    "content": json.dumps(result, ensure_ascii=False) if isinstance(result, dict) else str(result),
                })

                logger.info(f"[{self._agent_name}] 도구 실행: {original_tool_name} -> 성공: {success}")

            # tool_result 메시지 추가 (이전 도구 결과가 자동으로 다음 라운드의 컨텍스트가 됨)
            messages.append({"role": "user", "content": tool_results})

            # REMOVE_TOOL_DETAILS 자동 압축: 메시지 수 기반 빠른 체크 (O(1))
            # 평균 메시지 2000자 기준, 120개 이상이면 임계값 초과 가능성 높음
            if len(messages) > 120 and sum(len(str(m.get("content", ""))) for m in messages) > _CTX_COMPRESS_THRESHOLD_CHARS:
                from jinxus.core.context_guard import get_context_guard, CompactionStrategy
                guard = get_context_guard()
                messages = guard.compact(messages, CompactionStrategy.REMOVE_TOOL_DETAILS)
                logger.info(
                    f"[{self._agent_name}] 컨텍스트 자동 압축 (REMOVE_TOOL_DETAILS): "
                    f"{total_chars}자 → {sum(len(str(m.get('content',''))) for m in messages)}자"
                )

            # 멀티턴 도구 체이닝: 이전 도구의 출력을 요약하여 다음 라운드 힌트 제공
            if len(all_tool_calls) > 1 and round_num < self._max_rounds - 1:
                chain_summary = " → ".join(
                    f"{tc.tool_name}({'성공' if r.get('success') else '실패'})"
                    for tc, r in zip(all_tool_calls[-len(tool_uses):], all_raw_results[-len(tool_uses):])
                )
                logger.debug(f"[{self._agent_name}] 도구 체인: {chain_summary}")

        # max_rounds 도달 → None 반환하여 continuation 트리거
        logger.info(f"[{self._agent_name}] max_rounds({self._max_rounds}) 도달, continuation 시도")
        return None

    async def _execute_tool(self, tool_name: str, arguments: dict) -> dict:
        """단일 도구 실행

        Args:
            tool_name: 도구 이름 (Claude API 형식, 언더스코어 사용)
            arguments: 도구 인자

        Returns:
            실행 결과 딕셔너리
        """
        # 사전 검증: filesystem 도구에 URL 전달 방지
        if "filesystem" in tool_name:
            for val in arguments.values():
                if isinstance(val, str) and (val.startswith("http://") or val.startswith("https://")):
                    logger.warning(f"[{self._agent_name}] filesystem 도구에 URL 전달 차단: {val[:100]}")
                    return {
                        "success": False,
                        "error": f"URL은 filesystem 도구로 접근할 수 없습니다. github_agent, github_graphql, 또는 mcp__fetch__* 도구를 사용하세요.",
                        "output": None,
                    }

        tools = self._get_available_tools()

        # Claude API 형식 이름을 원래 형식으로 복원
        original_name = self._restore_tool_name(tool_name)

        if original_name not in tools:
            return {
                "success": False,
                "error": f"도구를 찾을 수 없음: {original_name}",
                "output": None,
            }

        tool = tools[original_name]

        try:
            # MCP 도구인 경우 (mcp: 프리픽스)
            if original_name.startswith("mcp:"):
                result = await tool.run(arguments)
            else:
                # 기존 도구: input 키로 전달하거나 전체 arguments 전달
                if "input" in arguments:
                    result = await tool.run(arguments["input"])
                else:
                    result = await tool.run(arguments)

            # ToolResult 객체 처리
            if hasattr(result, '__dict__'):
                return {
                    "success": getattr(result, 'success', True),
                    "output": getattr(result, 'output', str(result)),
                    "score": getattr(result, 'score', 0.8),
                    "error": getattr(result, 'error', None),
                }
            elif isinstance(result, dict):
                return result
            else:
                return {
                    "success": True,
                    "output": str(result),
                    "score": 0.8,
                }

        except Exception as e:
            logger.error(f"도구 실행 실패 [{original_name}]: {e}")
            return {
                "success": False,
                "error": str(e),
                "output": None,
            }


# 에이전트별 executor 캐시 (thread-safe)
_executors: dict[str, DynamicToolExecutor] = {}
_executors_lock = threading.Lock()


def get_dynamic_executor(agent_name: str) -> DynamicToolExecutor:
    """에이전트용 DynamicToolExecutor 싱글톤 반환 (thread-safe)"""
    if agent_name not in _executors:
        with _executors_lock:
            if agent_name not in _executors:  # double-check locking
                _executors[agent_name] = DynamicToolExecutor(agent_name=agent_name)
    return _executors[agent_name]
