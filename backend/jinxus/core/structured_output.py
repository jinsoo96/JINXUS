"""Structured Output 2단계 재시도 유틸 (Geny 패턴)

Pydantic 스키마 주입 → LLM 호출 → 검증 실패 시 correction prompt 재시도.
미션 분류, TODO 생성, 리뷰 결과 등 JSON 파싱 신뢰도 향상.
"""
import json
import logging
import re
from typing import Type, TypeVar, Optional

from pydantic import BaseModel, ValidationError
from anthropic import AsyncAnthropic

from jinxus.config import get_settings

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


def _extract_json(text: str) -> Optional[str]:
    """텍스트에서 JSON 부분 추출 (코드 블록, 순수 JSON 등)"""
    stripped = text.strip()

    # 마크다운 코드 블록
    for marker in ["```json", "```"]:
        if marker in stripped:
            try:
                extracted = stripped.split(marker, 1)[1].split("```", 1)[0].strip()
                json.loads(extracted)  # 검증
                return extracted
            except (json.JSONDecodeError, IndexError):
                pass

    # 직접 파싱
    try:
        json.loads(stripped)
        return stripped
    except json.JSONDecodeError:
        pass

    # 정규식 JSON 객체 추출
    match = re.search(r'\{.*\}', stripped, re.DOTALL)
    if match:
        try:
            json.loads(match.group())
            return match.group()
        except json.JSONDecodeError:
            pass

    # JSON 배열
    match = re.search(r'\[.*\]', stripped, re.DOTALL)
    if match:
        try:
            json.loads(match.group())
            return match.group()
        except json.JSONDecodeError:
            pass

    return None


async def resilient_structured_invoke(
    schema: Type[T],
    system_prompt: str,
    user_prompt: str,
    model: Optional[str] = None,
    max_retries: int = 1,
    fallback: Optional[T] = None,
) -> Optional[T]:
    """구조화된 LLM 출력 + 2단계 재시도

    1단계: 스키마 주입 → LLM 호출 → Pydantic 검증
    2단계: 실패 시 에러 메시지 포함 correction prompt로 재호출

    Args:
        schema: Pydantic 모델 클래스
        system_prompt: 시스템 프롬프트
        user_prompt: 사용자 프롬프트
        model: 사용할 모델 (None이면 settings에서)
        max_retries: 최대 재시도 횟수
        fallback: 전부 실패 시 반환값

    Returns:
        파싱된 Pydantic 모델 인스턴스 or fallback
    """
    settings = get_settings()
    client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    model = model or settings.claude_fast_model

    # 스키마 JSON 생성
    schema_json = json.dumps(schema.model_json_schema(), indent=2, ensure_ascii=False)

    full_system = (
        f"{system_prompt}\n\n"
        f"응답은 반드시 아래 JSON 스키마를 따르는 순수 JSON만 출력하라. "
        f"마크다운이나 설명 없이 JSON만:\n{schema_json}"
    )

    last_error = None
    last_raw = None

    for attempt in range(1 + max_retries):
        try:
            if attempt == 0:
                messages = [{"role": "user", "content": user_prompt}]
            else:
                # correction prompt
                messages = [
                    {"role": "user", "content": user_prompt},
                    {"role": "assistant", "content": last_raw or ""},
                    {
                        "role": "user",
                        "content": (
                            f"위 응답이 스키마 검증에 실패했습니다.\n"
                            f"오류: {last_error}\n\n"
                            f"올바른 JSON 스키마에 맞춰 다시 출력해주세요. JSON만 출력:"
                        ),
                    },
                ]

            response = await client.messages.create(
                model=model,
                max_tokens=2000,
                system=full_system,
                messages=messages,
            )

            raw_text = response.content[0].text.strip()
            last_raw = raw_text

            # JSON 추출
            json_str = _extract_json(raw_text)
            if not json_str:
                last_error = "JSON을 찾을 수 없음"
                logger.warning(
                    f"[StructuredOutput] JSON 추출 실패 (시도 {attempt + 1}): {raw_text[:200]}"
                )
                continue

            # Pydantic 검증
            data = json.loads(json_str)
            return schema.model_validate(data)

        except ValidationError as e:
            last_error = str(e)[:500]
            logger.warning(
                f"[StructuredOutput] Pydantic 검증 실패 (시도 {attempt + 1}): {last_error[:200]}"
            )
        except json.JSONDecodeError as e:
            last_error = f"JSON 파싱 오류: {e}"
            logger.warning(
                f"[StructuredOutput] JSON 파싱 실패 (시도 {attempt + 1}): {last_error}"
            )
        except Exception as e:
            last_error = str(e)
            logger.error(f"[StructuredOutput] LLM 호출 실패 (시도 {attempt + 1}): {e}")
            break  # API 에러는 재시도 무의미

    logger.warning(f"[StructuredOutput] 모든 시도 실패, fallback 사용: {schema.__name__}")
    return fallback
