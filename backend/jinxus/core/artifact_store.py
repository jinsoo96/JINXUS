"""Artifact Store v1.0.0 — 페이즈 간 아티팩트 공유

프로젝트 페이즈가 생성한 산출물(파일, 데이터, 코드)을 구조화하여 저장하고,
후속 페이즈에서 텍스트 요약 대신 실제 아티팩트를 참조할 수 있게 한다.

아티팩트 유형:
- file: 파일 경로 (코드, 문서, 이미지 등)
- data: 구조화된 데이터 (JSON, 분석 결과 등)
- code: 코드 조각 (함수, 클래스 등)
- report: 분석/리서치 보고서 텍스트

저장소: Redis (TTL 7일)
키 구조: jinxus:artifacts:{project_id}:{phase_id}
"""
import json
import logging
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class ArtifactType(str, Enum):
    FILE = "file"       # 파일 경로
    DATA = "data"       # JSON 데이터
    CODE = "code"       # 코드 조각
    REPORT = "report"   # 텍스트 보고서


@dataclass
class Artifact:
    """단일 아티팩트"""
    id: str                          # 아티팩트 고유 ID
    name: str                        # 이름 (예: "main.py", "분석 결과")
    artifact_type: str               # ArtifactType 값
    content: str                     # 실제 내용 (파일 경로 / JSON / 코드 / 텍스트)
    phase_id: str                    # 생성한 페이즈 ID
    phase_name: str = ""             # 페이즈 이름
    description: str = ""            # 설명
    metadata: dict = field(default_factory=dict)  # 추가 메타데이터
    created_at: str = ""


# Redis 키 패턴
_ARTIFACT_KEY = "jinxus:artifacts:{project_id}"
_ARTIFACT_TTL = 7 * 86400  # 7일


class ArtifactStore:
    """프로젝트 아티팩트 저장소

    페이즈 간 산출물 공유를 위한 중앙 저장소.
    Redis에 프로젝트 단위로 저장하며, 페이즈 ID로 필터링 가능.
    """

    def __init__(self):
        self._redis = None

    async def _get_redis(self):
        if self._redis is None:
            import redis.asyncio as aioredis
            from jinxus.config import get_settings
            settings = get_settings()
            self._redis = aioredis.Redis(
                host=settings.redis_host,
                port=settings.redis_port,
                password=settings.redis_password if settings.redis_password else None,
                decode_responses=True,
            )
        return self._redis

    async def save_artifact(
        self,
        project_id: str,
        phase_id: str,
        artifact_id: str,
        name: str,
        artifact_type: ArtifactType,
        content: str,
        phase_name: str = "",
        description: str = "",
        metadata: dict | None = None,
    ) -> Artifact:
        """아티팩트 저장"""
        artifact = Artifact(
            id=artifact_id,
            name=name,
            artifact_type=artifact_type.value,
            content=content,
            phase_id=phase_id,
            phase_name=phase_name,
            description=description,
            metadata=metadata or {},
            created_at=datetime.now().isoformat(),
        )

        try:
            redis = await self._get_redis()
            key = _ARTIFACT_KEY.format(project_id=project_id)

            # 기존 아티팩트 로드
            raw = await redis.get(key)
            artifacts = json.loads(raw) if raw else []

            # 중복 제거 (같은 ID면 교체)
            artifacts = [a for a in artifacts if a["id"] != artifact_id]
            artifacts.append(asdict(artifact))

            await redis.set(
                key,
                json.dumps(artifacts, ensure_ascii=False),
                ex=_ARTIFACT_TTL,
            )

            logger.info(
                f"[ArtifactStore] 저장: {project_id[:8]}/{phase_id} "
                f"→ {name} ({artifact_type.value})"
            )
            return artifact

        except Exception as e:
            logger.warning(f"[ArtifactStore] 저장 실패: {e}")
            return artifact

    async def get_artifacts(
        self,
        project_id: str,
        phase_id: str | None = None,
        artifact_type: ArtifactType | None = None,
    ) -> list[Artifact]:
        """아티팩트 조회

        Args:
            project_id: 프로젝트 ID
            phase_id: 특정 페이즈의 아티팩트만 (None이면 전체)
            artifact_type: 특정 유형만 (None이면 전체)
        """
        try:
            redis = await self._get_redis()
            key = _ARTIFACT_KEY.format(project_id=project_id)
            raw = await redis.get(key)
            if not raw:
                return []

            artifacts_data = json.loads(raw)
            artifacts = []

            for a in artifacts_data:
                if phase_id and a.get("phase_id") != phase_id:
                    continue
                if artifact_type and a.get("artifact_type") != artifact_type.value:
                    continue
                artifacts.append(Artifact(**a))

            return artifacts

        except Exception as e:
            logger.warning(f"[ArtifactStore] 조회 실패: {e}")
            return []

    async def get_phase_artifacts_summary(
        self,
        project_id: str,
        phase_ids: list[str],
        max_content_len: int = 2000,
    ) -> str:
        """선행 페이즈들의 아티팩트를 컨텍스트 문자열로 조합

        Args:
            project_id: 프로젝트 ID
            phase_ids: 선행 페이즈 ID 목록
            max_content_len: 아티팩트 내용 최대 길이

        Returns:
            후속 페이즈에 주입할 아티팩트 컨텍스트 문자열
        """
        all_artifacts = await self.get_artifacts(project_id)
        if not all_artifacts:
            return ""

        # 요청된 페이즈의 아티팩트만 필터
        relevant = [a for a in all_artifacts if a.phase_id in phase_ids]
        if not relevant:
            return ""

        parts = ["[선행 페이즈 아티팩트]"]
        for a in relevant:
            content_preview = a.content[:max_content_len]
            if len(a.content) > max_content_len:
                content_preview += "... (truncated)"

            if a.artifact_type == ArtifactType.FILE.value:
                parts.append(
                    f"\n📁 [{a.phase_name}] 파일: {a.name}"
                    f"\n   경로: {content_preview}"
                    f"\n   설명: {a.description}"
                )
            elif a.artifact_type == ArtifactType.CODE.value:
                parts.append(
                    f"\n💻 [{a.phase_name}] 코드: {a.name}"
                    f"\n```\n{content_preview}\n```"
                )
            elif a.artifact_type == ArtifactType.DATA.value:
                parts.append(
                    f"\n📊 [{a.phase_name}] 데이터: {a.name}"
                    f"\n{content_preview}"
                )
            elif a.artifact_type == ArtifactType.REPORT.value:
                parts.append(
                    f"\n📝 [{a.phase_name}] 보고서: {a.name}"
                    f"\n{content_preview}"
                )

        return "\n".join(parts)

    async def delete_project_artifacts(self, project_id: str) -> int:
        """프로젝트의 모든 아티팩트 삭제"""
        try:
            redis = await self._get_redis()
            key = _ARTIFACT_KEY.format(project_id=project_id)
            result = await redis.delete(key)
            if result:
                logger.info(f"[ArtifactStore] 프로젝트 아티팩트 삭제: {project_id[:8]}")
            return result
        except Exception as e:
            logger.warning(f"[ArtifactStore] 삭제 실패: {e}")
            return 0

    async def close(self) -> None:
        """Redis 연결 종료"""
        if self._redis:
            try:
                await self._redis.close()
            except Exception as e:
                logger.debug(f"[ArtifactStore] Redis 종료 중 오류: {e}")
            self._redis = None

    async def extract_artifacts_from_result(
        self,
        project_id: str,
        phase_id: str,
        phase_name: str,
        result_text: str,
    ) -> list[Artifact]:
        """페이즈 실행 결과에서 아티팩트를 자동 추출하여 저장

        결과 텍스트에서 파일 경로, 코드 블록 등을 감지하여 아티팩트로 저장한다.
        """
        import re
        import uuid

        artifacts = []

        # 1. 파일 경로 추출 (/home/..., ./... 패턴)
        file_patterns = re.findall(
            r'(?:^|\s)((?:/home/|/tmp/|/var/|\./)[\w/.\-]+\.\w+)',
            result_text,
        )
        seen_files = set()
        for fp in file_patterns:
            if fp in seen_files:
                continue
            seen_files.add(fp)
            artifact = await self.save_artifact(
                project_id=project_id,
                phase_id=phase_id,
                artifact_id=str(uuid.uuid4())[:8],
                name=fp.split("/")[-1],
                artifact_type=ArtifactType.FILE,
                content=fp,
                phase_name=phase_name,
                description=f"페이즈 '{phase_name}'에서 생성/참조된 파일",
            )
            artifacts.append(artifact)

        # 2. 코드 블록 추출 (```...```)
        code_blocks = re.findall(r'```(\w*)\n(.*?)```', result_text, re.DOTALL)
        for i, (lang, code) in enumerate(code_blocks[:5]):  # 최대 5개
            if len(code.strip()) < 20:  # 너무 짧은 코드 블록 무시
                continue
            artifact = await self.save_artifact(
                project_id=project_id,
                phase_id=phase_id,
                artifact_id=str(uuid.uuid4())[:8],
                name=f"code_block_{i+1}.{lang or 'txt'}",
                artifact_type=ArtifactType.CODE,
                content=code.strip()[:5000],
                phase_name=phase_name,
                description=f"페이즈 '{phase_name}'에서 생성된 코드 ({lang or 'unknown'})",
                metadata={"language": lang or "unknown"},
            )
            artifacts.append(artifact)

        # 3. 결과 전체를 보고서 아티팩트로 저장 (500자 이상일 때)
        if len(result_text) > 500:
            artifact = await self.save_artifact(
                project_id=project_id,
                phase_id=phase_id,
                artifact_id=f"report_{phase_id}",
                name=f"{phase_name} 결과 보고서",
                artifact_type=ArtifactType.REPORT,
                content=result_text[:10000],
                phase_name=phase_name,
                description=f"페이즈 '{phase_name}'의 전체 실행 결과",
            )
            artifacts.append(artifact)

        if artifacts:
            logger.info(
                f"[ArtifactStore] 자동 추출: {phase_name} → {len(artifacts)}개 아티팩트"
            )

        return artifacts


# 싱글톤
_instance: ArtifactStore | None = None


def get_artifact_store() -> ArtifactStore:
    global _instance
    if _instance is None:
        _instance = ArtifactStore()
    return _instance
