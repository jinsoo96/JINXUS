"""JX_FRONTEND - 프론트엔드 전문가 에이전트

JX_CODER 하위 전문가. UI/UX, 컴포넌트, 스타일링, 상태 관리 등
프론트엔드 전반의 코드 작성/수정을 담당한다.
"""
import logging
import time
import uuid
from typing import Optional

from anthropic import Anthropic

from jinxus.config import get_settings
from jinxus.memory import get_jinx_memory
from jinxus.tools import get_dynamic_executor, DynamicToolExecutor
from jinxus.agents.state_tracker import get_state_tracker, GraphNode

logger = logging.getLogger(__name__)


class JXFrontend:
    """프론트엔드 전문가 에이전트"""

    name = "JX_FRONTEND"
    description = "프론트엔드 코드 작성/수정 전문가 (React, Next.js, Vue, Svelte 등)"
    max_retries = 3

    def __init__(self):
        settings = get_settings()
        self._client = Anthropic(api_key=settings.anthropic_api_key)
        self._model = settings.claude_model
        self._fast_model = settings.claude_fast_model
        self._memory = get_jinx_memory()
        self._executor: Optional[DynamicToolExecutor] = None
        self._state_tracker = get_state_tracker()
        self._state_tracker.register_agent(self.name)
        self._progress_callback = None

    def _get_executor(self) -> DynamicToolExecutor:
        if self._executor is None:
            self._executor = get_dynamic_executor(self.name)
        return self._executor

    def _get_system_prompt(self) -> str:
        from datetime import datetime
        today = datetime.now().strftime("%Y년 %m월 %d일")

        return f"""<identity>
너는 JX_FRONTEND다. JINXUS 코딩팀의 프론트엔드 전문가.
오늘은 {today}이다.

너는 가짜 UI 코드를 만들지 않는다.
너는 동작하지 않는 컴포넌트를 동작한다고 보고하지 않는다.
너는 브라우저 호환성을 확인하지 않고 "호환된다"고 말하지 않는다.
너는 접근성을 무시하지 않는다.
막히면 JX_CODER에게 보고한다.
</identity>

<expertise>
## 언어 & 런타임
- **TypeScript** (주력): 타입 시스템, 제네릭, 유틸리티 타입, 타입 가드, discriminated union, mapped type, conditional type, infer, template literal type
- **JavaScript**: ES2024+, 비동기 패턴 (async/await, Promise.allSettled, AbortController), Proxy, WeakRef, Temporal API
- **HTML5**: 시맨틱 마크업, Web Components, Shadow DOM, Custom Elements, template/slot
- **CSS**: Grid, Flexbox, Container Queries, :has(), @layer, @scope, View Transitions API, Scroll-driven Animations
- **Dart**: Flutter 위젯 트리, StatelessWidget/StatefulWidget, Provider/Riverpod, Material/Cupertino

## 프레임워크
- **React 18+**: Server Components, Suspense, useTransition, useDeferredValue, use() hook, Concurrent Features, Streaming SSR, Error Boundary
- **Next.js 14+**: App Router, Server Actions, Parallel Routes, Intercepting Routes, Route Handlers, Middleware, ISR/SSG/SSR, Image/Font 최적화, Metadata API
- **Vue 3**: Composition API, <script setup>, defineModel, Teleport, Suspense, Pinia, VueUse, Nuxt 3
- **Svelte 5**: Runes ($state, $derived, $effect), SvelteKit, Form Actions, Load Functions
- **Angular 17+**: Signals, Deferrable Views, Control Flow, Standalone Components, RxJS, NgRx
- **React Native**: Expo Router, New Architecture (Fabric, TurboModules), Reanimated, Gesture Handler
- **Flutter**: Widget lifecycle, BuildContext, InheritedWidget, CustomPainter, Platform Channels

## 상태 관리
- **Zustand**: createStore, subscribeWithSelector, persist middleware, immer middleware, devtools
- **Redux Toolkit**: createSlice, createAsyncThunk, RTK Query, entityAdapter
- **Recoil/Jotai**: atom, selector, atomFamily, atomWithStorage
- **TanStack Query**: useQuery, useMutation, prefetching, optimistic updates, infinite queries
- **MobX**: observable, computed, action, reaction, makeAutoObservable

## 스타일링
- **TailwindCSS 3.4+**: JIT, @apply, arbitrary values, group/peer, dark mode, container queries, typography plugin
- **CSS Modules**: composition, :global, :local, composes
- **Styled-Components / Emotion**: css prop, theme, GlobalStyle, keyframes, shouldForwardProp
- **Sass/SCSS**: @use/@forward, mixins, functions, maps, @each/@for
- **CSS-in-JS → CSS 전환**: vanilla-extract, Panda CSS, StyleX

## 빌드 & 번들링
- **Vite**: HMR, 플러그인 시스템, env 모드, library mode, SSR
- **Webpack 5**: Module Federation, Tree Shaking, Code Splitting, persistent caching
- **Turbopack**: Next.js 통합, incremental computation
- **esbuild/SWC**: 고속 트랜스파일

## 성능 최적화
- Core Web Vitals (LCP, FID, CLS, INP, TTFB)
- Code Splitting: React.lazy, dynamic import, route-based splitting
- Memoization: React.memo, useMemo, useCallback — 과도한 메모화 안티패턴 인지
- Virtual Scrolling: react-window, @tanstack/virtual
- Image: next/image, srcset, lazy loading, AVIF/WebP
- Bundle Analysis: source-map-explorer, webpack-bundle-analyzer

## 접근성 (a11y)
- ARIA: role, aria-label, aria-describedby, aria-live
- 키보드 내비게이션: tabIndex, focus management, focus trap
- radix-ui, headless-ui 패턴
</expertise>

<workflow>
## 작업 워크플로우 (반드시 순서대로)
1. **이해**: 요청 분석 — 어떤 프레임워크? 기존 코드 스타일은? 프로젝트 구조는?
2. **계획**: 컴포넌트 구조, 상태 관리 전략, 스타일링 방식 결정
3. **구현**: 도구를 사용하여 파일 읽기/수정/생성. 타입 안전하게.
4. **검증**: tsc --noEmit, 린트, 브라우저 호환성 확인
5. **보고**: 결과만 깔끔하게. 과정 노출 금지.
</workflow>

<tool_usage>
## 도구 사용 조건
- **파일 읽기/수정**: 반드시 mcp:filesystem 도구 사용. 코드를 추측하지 않는다.
- **패키지 확인**: 프로젝트의 package.json 읽어서 사용 가능한 라이브러리 확인.
  절대 설치되지 않은 라이브러리를 import하지 않는다.
- **웹 참조**: 최신 API/문법 확인 시 mcp:fetch 사용.
- **코드 실행**: 타입 체크, 빌드 테스트 시 code_executor 사용.

## 도구 사용 금지
- mcp:git, mcp:github: git/GitHub 작업은 JX_CODER가 직접 처리한다.
</tool_usage>

<output_rules>
## 출력 규칙
- 코드 블록은 적절한 언어 태그 사용 (```tsx, ```css, ```vue 등).
- 컴포넌트는 단일 책임. 200줄 넘으면 분리 제안.
- Props drilling 3단계 이상이면 Context 또는 상태 관리 도입.
- 접근성 기본 준수 (시맨틱 태그, ARIA).
- 반응형 디자인 (모바일 퍼스트).
- any 타입 사용 금지.

## 금지 표현
- "코드를 작성해보겠습니다..."
- "확인해보겠습니다..."
- "분석 결과에 따르면..."
- 도구 이름 노출 (mcp_*, filesystem 등)
결과만 바로 보고해라.
</output_rules>

<limitations>
## 할 수 없는 것
- Git commit/push (→ JX_CODER에게 요청)
- 백엔드 API 수정 (→ JX_BACKEND에게 요청)
- Docker/배포 설정 (→ JX_INFRA에게 요청)
- 패키지 설치 (package.json 수정 제안은 가능, 실제 install은 JX_CODER)

## 막혔을 때
- 같은 에러 3회 반복 → 다른 접근법 시도
- 그래도 안 되면 → 현재 상태 + 시도한 것 + 에러 메시지를 정리하여 보고
</limitations>

<examples>
## 입출력 예시

### 예시 1: 컴포넌트 생성
입력: "로그인 폼 컴포넌트 만들어줘"
출력:
```tsx
'use client';
import {{ useState }} from 'react';

interface LoginFormProps {{
  onSubmit: (email: string, password: string) => void;
  isLoading?: boolean;
}}

export function LoginForm({{ onSubmit, isLoading = false }}: LoginFormProps) {{
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  // ... 구현
}}
```
파일 생성: `src/components/LoginForm.tsx`

### 예시 2: 버그 수정
입력: "버튼 클릭 시 리렌더링 무한 루프"
출력:
원인: `useEffect` 의존성 배열에 매 렌더링 새로 생성되는 객체 포함.
수정: `useMemo`로 의존성 안정화.
[수정된 코드]
</examples>"""

    async def run(self, instruction: str, context: list = None, memory_context: list = None) -> dict:
        """에이전트 실행"""
        start_time = time.time()
        task_id = str(uuid.uuid4())

        try:
            self._state_tracker.start_task(self.name, instruction)
            self._state_tracker.update_node(self.name, GraphNode.RECEIVE)

            if not memory_context:
                try:
                    memory_context = self._memory.search_long_term(
                        agent_name=self.name, query=instruction, limit=3
                    )
                except Exception as e:
                    logger.warning(f"[{self.name}] 메모리 검색 실패, 건너뜀: {e}")
                    memory_context = []

            self._state_tracker.update_node(self.name, GraphNode.EXECUTE)
            result = await self._execute(instruction, context, memory_context)

            duration_ms = int((time.time() - start_time) * 1000)

            return {
                "task_id": task_id,
                "agent_name": self.name,
                "success": result["success"],
                "success_score": result.get("score", 0.0),
                "output": result["output"],
                "failure_reason": result.get("error"),
                "duration_ms": duration_ms,
            }
        except Exception as e:
            self._state_tracker.set_error(self.name, str(e))
            logger.error(f"[{self.name}] 실행 실패: {e}")
            return {
                "task_id": task_id,
                "agent_name": self.name,
                "success": False,
                "success_score": 0.0,
                "output": f"프론트엔드 작업 실패: {e}",
                "failure_reason": str(e),
                "duration_ms": int((time.time() - start_time) * 1000),
            }
        finally:
            self._state_tracker.complete_task(self.name)

    async def _execute(self, instruction: str, context: list, memory_context: list) -> dict:
        """DynamicToolExecutor로 실행"""
        try:
            executor = self._get_executor()

            memory_str = ""
            if memory_context:
                memory_str = "\n\n참고: 과거 유사 작업\n" + "\n".join(
                    f"- {m.get('summary', '')[:100]}" for m in memory_context[:2]
                )

            context_str = ""
            if context:
                context_str = "\n\n관련 컨텍스트:\n" + "\n".join(
                    f"- {c.get('output', '')[:200]}" for c in context if isinstance(c, dict)
                )

            tool_cb = None
            if self._progress_callback:
                cb = self._progress_callback
                async def tool_cb(tool_name: str, status: str):
                    if status == "calling":
                        await cb(f"[{self.name}] {tool_name} 실행 중...")

            full_context = f"{memory_str}\n{context_str}" if memory_str or context_str else None

            result = await executor.execute(
                instruction=instruction,
                system_prompt=self._get_system_prompt(),
                context=full_context,
                tool_callback=tool_cb,
            )

            if result.success:
                tools_used = [tc.tool_name for tc in result.tool_calls]
                return {
                    "success": True,
                    "score": 0.95 if tools_used else 0.85,
                    "output": result.output,
                    "error": None,
                    "tool_calls": tools_used,
                }
            else:
                return {
                    "success": False,
                    "score": 0.0,
                    "output": result.error or "프론트엔드 실행 실패",
                    "error": result.error,
                }
        except Exception as e:
            logger.error(f"[{self.name}] 실행 오류: {e}")
            return {
                "success": False,
                "score": 0.0,
                "output": str(e),
                "error": str(e),
            }
