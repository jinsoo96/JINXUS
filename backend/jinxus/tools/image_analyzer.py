"""이미지 분석 도구 - Claude Vision API 기반"""
import base64
import logging
from pathlib import Path

import httpx

from .base import JinxTool, ToolResult
from jinxus.config import get_settings

logger = logging.getLogger("jinxus.tools.image_analyzer")

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 5MB


class ImageAnalyzer(JinxTool):
    """Claude Vision API를 이용한 이미지 분석 도구"""

    name = "image_analyzer"
    description = "이미지 파일 또는 URL을 분석합니다. 텍스트 추출, 내용 설명, 차트 해석 등 지원"
    allowed_agents = []  # 모든 에이전트 허용
    input_schema = {
        "type": "object",
        "properties": {
            "source": {
                "type": "string",
                "description": "이미지 파일 경로 또는 URL"
            },
            "prompt": {
                "type": "string",
                "description": "이미지에 대한 질문 또는 지시사항 (예: '이 차트의 수치를 알려줘', '텍스트를 추출해줘')",
                "default": "이 이미지의 내용을 상세히 설명해주세요."
            }
        },
        "required": ["source"]
    }

    def __init__(self):
        super().__init__()
        settings = get_settings()
        self._api_key = settings.anthropic_api_key

    async def run(self, input_data: dict) -> ToolResult:
        self._start_timer()

        source = input_data.get("source", "").strip()
        if not source:
            return ToolResult(
                success=False,
                output=None,
                error="source(파일 경로 또는 URL)가 필요합니다",
                duration_ms=self._get_duration_ms(),
            )

        prompt = input_data.get("prompt", "이 이미지의 내용을 상세히 설명해주세요.")

        try:
            if source.startswith("http://") or source.startswith("https://"):
                image_block = await self._load_from_url(source)
            else:
                image_block = self._load_from_file(source)

            result = await self._analyze(image_block, prompt)
            return ToolResult(
                success=True,
                output={"source": source, "analysis": result},
                duration_ms=self._get_duration_ms(),
            )
        except ValueError as e:
            return ToolResult(
                success=False,
                output=None,
                error=str(e),
                duration_ms=self._get_duration_ms(),
            )
        except Exception as e:
            logger.error(f"이미지 분석 실패 ({source}): {e}")
            return ToolResult(
                success=False,
                output=None,
                error=str(e),
                duration_ms=self._get_duration_ms(),
            )

    def _load_from_file(self, path_str: str) -> dict:
        """로컬 파일 → base64 인코딩 이미지 블록"""
        path = Path(path_str).expanduser().resolve()
        if not path.exists():
            raise ValueError(f"파일을 찾을 수 없습니다: {path}")

        ext = path.suffix.lower()
        if ext not in SUPPORTED_EXTENSIONS:
            raise ValueError(f"지원하지 않는 이미지 형식: {ext} (지원: {', '.join(SUPPORTED_EXTENSIONS)})")

        size = path.stat().st_size
        if size > MAX_IMAGE_BYTES:
            raise ValueError(f"이미지 크기 초과: {size // 1024}KB (최대 5MB)")

        data = path.read_bytes()
        media_type = self._ext_to_media_type(ext)

        return {
            "type": "base64",
            "media_type": media_type,
            "data": base64.standard_b64encode(data).decode("utf-8"),
        }

    async def _load_from_url(self, url: str) -> dict:
        """URL → base64 인코딩 이미지 블록"""
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()

        content_type = resp.headers.get("content-type", "image/jpeg").split(";")[0].strip()
        if not content_type.startswith("image/"):
            raise ValueError(f"이미지 URL이 아닙니다: {content_type}")

        data = resp.content
        if len(data) > MAX_IMAGE_BYTES:
            raise ValueError(f"이미지 크기 초과: {len(data) // 1024}KB (최대 5MB)")

        return {
            "type": "base64",
            "media_type": content_type,
            "data": base64.standard_b64encode(data).decode("utf-8"),
        }

    async def _analyze(self, image_block: dict, prompt: str) -> str:
        """Claude Vision API 호출"""
        settings = get_settings()
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        body = {
            "model": settings.claude_fast_model,  # 비용 절약: haiku 사용
            "max_tokens": 1024,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": image_block,
                        },
                        {
                            "type": "text",
                            "text": prompt,
                        }
                    ]
                }
            ]
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers=headers,
                json=body,
            )
            resp.raise_for_status()
            data = resp.json()

        return data["content"][0]["text"]

    @staticmethod
    def _ext_to_media_type(ext: str) -> str:
        mapping = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".webp": "image/webp",
        }
        return mapping.get(ext, "image/jpeg")
