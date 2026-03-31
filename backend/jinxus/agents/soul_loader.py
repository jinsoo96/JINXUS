"""SOUL.md 에이전트 인격 파일 로더 (Paperclip 패턴)

data/souls/{agent}/ 디렉토리에서 에이전트 인격 파일을 로드.
SOUL.md(성격) + RULES.md(행동규칙)로 분리된 파일 기반 페르소나.
런타임 편집 가능, 에이전트 자기학습에 활용.
"""
import logging
from pathlib import Path
from typing import Optional

from jinxus.config import get_settings

logger = logging.getLogger(__name__)

# 캐시 (파일 변경 감지용)
_soul_cache: dict[str, dict[str, str]] = {}
_soul_mtimes: dict[str, float] = {}


def _souls_dir() -> Path:
    """souls 디렉토리 경로"""
    return get_settings().backend_root / "data" / "souls"


def load_soul(agent_name: str) -> Optional[str]:
    """에이전트의 SOUL.md 로드

    Returns:
        SOUL.md 내용 (없으면 None)
    """
    soul_path = _souls_dir() / agent_name / "SOUL.md"
    if not soul_path.exists():
        return None

    # 캐시 체크 (mtime 기반)
    cache_key = f"{agent_name}:soul"
    mtime = soul_path.stat().st_mtime
    if cache_key in _soul_cache and _soul_mtimes.get(cache_key) == mtime:
        return _soul_cache[cache_key].get("content")

    try:
        content = soul_path.read_text(encoding="utf-8")
        _soul_cache[cache_key] = {"content": content}
        _soul_mtimes[cache_key] = mtime
        return content
    except Exception as e:
        logger.warning(f"[SoulLoader] {agent_name} SOUL.md 로드 실패: {e}")
        return None


def load_rules(agent_name: str) -> Optional[str]:
    """에이전트의 RULES.md 로드"""
    rules_path = _souls_dir() / agent_name / "RULES.md"
    if not rules_path.exists():
        return None

    cache_key = f"{agent_name}:rules"
    mtime = rules_path.stat().st_mtime
    if cache_key in _soul_cache and _soul_mtimes.get(cache_key) == mtime:
        return _soul_cache[cache_key].get("content")

    try:
        content = rules_path.read_text(encoding="utf-8")
        _soul_cache[cache_key] = {"content": content}
        _soul_mtimes[cache_key] = mtime
        return content
    except Exception as e:
        logger.warning(f"[SoulLoader] {agent_name} RULES.md 로드 실패: {e}")
        return None


def get_soul_prompt(agent_name: str) -> str:
    """SOUL.md + RULES.md를 결합한 프롬프트 스니펫 생성

    파일이 없으면 빈 문자열 반환 (기존 personality.py 프롬프트가 fallback)
    """
    parts = []

    soul = load_soul(agent_name)
    if soul:
        parts.append(soul)

    rules = load_rules(agent_name)
    if rules:
        parts.append(rules)

    return "\n\n".join(parts)


def save_soul(agent_name: str, content: str) -> bool:
    """SOUL.md 저장 (런타임 편집)"""
    soul_dir = _souls_dir() / agent_name
    soul_dir.mkdir(parents=True, exist_ok=True)

    try:
        soul_path = soul_dir / "SOUL.md"
        soul_path.write_text(content, encoding="utf-8")

        # 캐시 무효화
        cache_key = f"{agent_name}:soul"
        _soul_cache.pop(cache_key, None)
        _soul_mtimes.pop(cache_key, None)

        logger.info(f"[SoulLoader] {agent_name} SOUL.md 저장 완료")
        return True
    except Exception as e:
        logger.error(f"[SoulLoader] {agent_name} SOUL.md 저장 실패: {e}")
        return False


def save_rules(agent_name: str, content: str) -> bool:
    """RULES.md 저장 (런타임 편집)"""
    soul_dir = _souls_dir() / agent_name
    soul_dir.mkdir(parents=True, exist_ok=True)

    try:
        rules_path = soul_dir / "RULES.md"
        rules_path.write_text(content, encoding="utf-8")

        cache_key = f"{agent_name}:rules"
        _soul_cache.pop(cache_key, None)
        _soul_mtimes.pop(cache_key, None)

        logger.info(f"[SoulLoader] {agent_name} RULES.md 저장 완료")
        return True
    except Exception as e:
        logger.error(f"[SoulLoader] {agent_name} RULES.md 저장 실패: {e}")
        return False


def list_agents_with_souls() -> list[str]:
    """SOUL.md가 있는 에이전트 목록"""
    souls_dir = _souls_dir()
    if not souls_dir.exists():
        return []

    return [
        d.name for d in souls_dir.iterdir()
        if d.is_dir() and (d / "SOUL.md").exists()
    ]


def clear_cache():
    """캐시 전체 초기화"""
    _soul_cache.clear()
    _soul_mtimes.clear()
