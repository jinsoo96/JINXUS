"""CLI 채널 — 터미널에서 JINXUS 직접 사용

사용법:
    # 직접 명령
    python -m channels.cli "파이썬으로 피보나치 수열 출력해줘"

    # 파이프
    cat error.log | python -m channels.cli "이 에러 분석해줘"

    # 파일 첨부
    python -m channels.cli "이 코드 리뷰해줘" --file ./src/model.py

    # 스트리밍
    python -m channels.cli --stream "FastAPI 서버 설계해줘"

    # pyproject.toml 설치 후
    jinxus "안녕?"
"""
import argparse
import asyncio
import sys
from typing import Optional

from jinxus.core.orchestrator import get_orchestrator


async def run_cli(
    message: str,
    file_path: Optional[str] = None,
    agent: Optional[str] = None,
    stream: bool = False,
    session_id: Optional[str] = None,
):
    """CLI 실행"""
    orchestrator = get_orchestrator()
    await orchestrator.initialize()

    # 파일 첨부
    if file_path:
        try:
            with open(file_path, encoding="utf-8") as f:
                file_content = f.read()
            message = f"{message}\n\n```\n{file_content}\n```"
        except Exception as e:
            print(f"파일 읽기 오류: {e}", file=sys.stderr)
            return

    # stdin 파이프 입력
    if not sys.stdin.isatty():
        stdin_content = sys.stdin.read()
        if stdin_content.strip():
            message = f"{message}\n\n{stdin_content}"

    # 특정 에이전트 지정 모드
    if agent:
        result = await _run_with_agent(agent, message)
        if result:
            print(result["output"])
            print(f"\n[에이전트: {result['agent_name']}]", file=sys.stderr)
        return

    # 스트리밍 모드
    if stream:
        async for event in orchestrator.run_task_stream(message, session_id):
            event_type = event.get("event")

            if event_type == "message":
                content = event.get("data", {}).get("content", "")
                print(content, end="", flush=True)

            elif event_type == "agent_started":
                agent_name = event.get("data", {}).get("agent", "")
                print(f"\n[{agent_name} 작동 중...]", file=sys.stderr, flush=True)

            elif event_type == "agent_done":
                agent_name = event.get("data", {}).get("agent", "")
                success = event.get("data", {}).get("success", False)
                status = "완료" if success else "실패"
                print(f"\n[{agent_name} {status}]", file=sys.stderr, flush=True)

            elif event_type == "done":
                print()  # 줄바꿈
    else:
        # 일반 모드
        result = await orchestrator.run_task(message, session_id)
        print(result["response"])

        # 사용된 에이전트 출력 (stderr)
        agents_used = result.get("agents_used", [])
        if agents_used:
            print(f"\n[에이전트: {', '.join(agents_used)}]", file=sys.stderr)


async def _run_with_agent(agent_name: str, message: str) -> Optional[dict]:
    """특정 에이전트 직접 실행

    Args:
        agent_name: 에이전트 이름 (JX_CODER, JX_RESEARCHER 등)
        message: 작업 지시

    Returns:
        에이전트 실행 결과 또는 None
    """
    from jinxus.agents import get_agent, register_all_agents

    # 에이전트 이름 정규화 (대문자, JX_ 접두사)
    normalized = agent_name.upper()
    if not normalized.startswith("JX_") and not normalized.startswith("JS_"):
        normalized = f"JX_{normalized}"

    # 에이전트 레지스트리 초기화
    register_all_agents()

    # 에이전트 조회
    agent = get_agent(normalized)
    if not agent:
        print(f"에이전트를 찾을 수 없음: {normalized}", file=sys.stderr)
        print("사용 가능: JX_CODER, JX_RESEARCHER, JX_WRITER, JX_ANALYST, JX_OPS, JS_PERSONA", file=sys.stderr)
        return None

    print(f"[{normalized} 직접 실행...]", file=sys.stderr, flush=True)

    try:
        result = await agent.run(message)
        return result
    except Exception as e:
        print(f"에이전트 실행 오류: {e}", file=sys.stderr)
        return None


def main():
    """CLI 진입점"""
    parser = argparse.ArgumentParser(
        description="JINXUS CLI - 터미널에서 AI 비서 사용",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  jinxus "안녕?"
  jinxus "코드 짜줘" --file ./script.py
  jinxus --stream "긴 작업 해줘"
  cat log.txt | jinxus "분석해줘"
        """,
    )

    parser.add_argument(
        "message",
        nargs="?",
        help="JINXUS에게 전달할 명령",
    )

    parser.add_argument(
        "--file", "-f",
        help="첨부할 파일 경로",
    )

    parser.add_argument(
        "--agent", "-a",
        help="특정 에이전트 직접 실행 (JX_CODER, JX_RESEARCHER, JS_PERSONA 등)",
    )

    parser.add_argument(
        "--stream", "-s",
        action="store_true",
        help="스트리밍 출력",
    )

    parser.add_argument(
        "--session", "-S",
        help="세션 ID (대화 연속성)",
    )

    parser.add_argument(
        "--interactive", "-i",
        action="store_true",
        help="대화형 모드",
    )

    args = parser.parse_args()

    # 대화형 모드
    if args.interactive:
        asyncio.run(interactive_mode())
        return

    # 메시지 필수
    if not args.message:
        # stdin 확인
        if sys.stdin.isatty():
            parser.print_help()
            sys.exit(1)
        else:
            args.message = ""  # stdin만 있는 경우

    asyncio.run(
        run_cli(
            message=args.message,
            file_path=args.file,
            agent=args.agent,
            stream=args.stream,
            session_id=args.session,
        )
    )


async def interactive_mode():
    """대화형 모드"""
    orchestrator = get_orchestrator()
    await orchestrator.initialize()

    session_id = None

    print("JINXUS 대화형 모드 (종료: exit, quit, 또는 Ctrl+C)")
    print("-" * 50)

    while True:
        try:
            user_input = input("\n주인님 > ").strip()

            if not user_input:
                continue

            if user_input.lower() in ["exit", "quit", "q"]:
                print("안녕히 가세요, 주인님!")
                break

            if user_input.lower() == "/status":
                status = await orchestrator.get_system_status()
                print(f"상태: {status}")
                continue

            if user_input.lower() == "/agents":
                agents = orchestrator.get_agents()
                print(f"에이전트: {', '.join(agents)}")
                continue

            # JINXUS 실행
            print("\nJINXUS > ", end="", flush=True)

            async for event in orchestrator.run_task_stream(user_input, session_id):
                event_type = event.get("event")

                if event_type == "start":
                    session_id = event.get("data", {}).get("session_id")

                elif event_type == "message":
                    content = event.get("data", {}).get("content", "")
                    print(content, end="", flush=True)

            print()  # 줄바꿈

        except KeyboardInterrupt:
            print("\n\n안녕히 가세요, 주인님!")
            break
        except EOFError:
            break


if __name__ == "__main__":
    main()
