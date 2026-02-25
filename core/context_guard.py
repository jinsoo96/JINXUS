"""컨텍스트 윈도우 관리 — 토큰 폭탄 방지

에이전트 output이 너무 길면 aggregate 시 컨텍스트 한도 초과 또는 과도한 과금 발생.
이 모듈로 output 길이를 제한한다.
"""

MAX_OUTPUT_CHARS = 4000   # 에이전트 output 최대 길이
MAX_CONTEXT_CHARS = 8000  # aggregate로 넘기는 최대 전체 길이


def truncate_output(output: str, max_chars: int = MAX_OUTPUT_CHARS) -> str:
    """에이전트 output 길이 제한

    Args:
        output: 원본 출력
        max_chars: 최대 글자 수

    Returns:
        잘린 출력 (중간 생략 표시 포함)
    """
    if not output:
        return ""

    if len(output) <= max_chars:
        return output

    half = max_chars // 2
    omitted = len(output) - max_chars
    return (
        output[:half]
        + f"\n\n... [중간 {omitted}자 생략] ...\n\n"
        + output[-half:]
    )


def guard_results(results: list[dict]) -> list[dict]:
    """aggregate 전에 각 에이전트 output 자르기

    Args:
        results: 에이전트 실행 결과 리스트

    Returns:
        output이 잘린 결과 리스트
    """
    guarded = []
    for r in results:
        guarded.append({
            **r,
            "output": truncate_output(r.get("output", "")),
        })
    return guarded


def guard_context(context: list[dict], max_chars: int = MAX_CONTEXT_CHARS) -> list[dict]:
    """순차 실행 시 컨텍스트 크기 제한

    Args:
        context: 이전 작업 결과 컨텍스트
        max_chars: 전체 컨텍스트 최대 크기

    Returns:
        크기 제한된 컨텍스트
    """
    if not context:
        return []

    total_chars = sum(len(c.get("summary", "")) for c in context)

    if total_chars <= max_chars:
        return context

    # 최신 것부터 유지하면서 크기 제한
    guarded = []
    current_chars = 0

    for c in reversed(context):
        summary = c.get("summary", "")
        if current_chars + len(summary) <= max_chars:
            guarded.insert(0, c)
            current_chars += len(summary)
        else:
            # 마지막 항목은 잘라서라도 포함
            remaining = max_chars - current_chars
            if remaining > 100:
                guarded.insert(0, {
                    **c,
                    "summary": summary[:remaining] + "...(생략)",
                })
            break

    return guarded
