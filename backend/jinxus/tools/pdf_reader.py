"""PDF 파일 읽기 도구 - pdfplumber 기반"""
import logging
from pathlib import Path

from .base import JinxTool, ToolResult

logger = logging.getLogger("jinxus.tools.pdf_reader")


class PDFReader(JinxTool):
    """PDF 파일 텍스트 추출 도구"""

    name = "pdf_reader"
    description = "PDF 파일에서 텍스트를 추출합니다. 페이지 범위 지정 가능"
    allowed_agents = []  # 모든 에이전트 허용
    input_schema = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "PDF 파일 경로 (절대 경로 또는 홈 기준 상대 경로)"
            },
            "pages": {
                "type": "string",
                "description": "추출할 페이지 범위 (예: '1-3', '1,2,5', '1' / 미지정 시 전체)"
            },
            "max_chars": {
                "type": "integer",
                "description": "최대 추출 글자 수 (기본: 10000)",
                "default": 10000
            }
        },
        "required": ["path"]
    }

    def __init__(self):
        super().__init__()
        try:
            import pdfplumber  # noqa: F401
            self._available = True
        except ImportError:
            self._available = False
            logger.warning("pdfplumber 미설치 — pip install pdfplumber")

    async def run(self, input_data: dict) -> ToolResult:
        self._start_timer()

        if not self._available:
            return ToolResult(
                success=False,
                output=None,
                error="pdfplumber 패키지가 설치되지 않았습니다. pip install pdfplumber",
                duration_ms=self._get_duration_ms(),
            )

        path_str = input_data.get("path", "")
        if not path_str:
            return ToolResult(
                success=False,
                output=None,
                error="path가 필요합니다",
                duration_ms=self._get_duration_ms(),
            )

        # 경로 정규화
        path = Path(path_str).expanduser().resolve()
        if not path.exists():
            return ToolResult(
                success=False,
                output=None,
                error=f"파일을 찾을 수 없습니다: {path}",
                duration_ms=self._get_duration_ms(),
            )
        if path.suffix.lower() != ".pdf":
            return ToolResult(
                success=False,
                output=None,
                error=f"PDF 파일이 아닙니다: {path.suffix}",
                duration_ms=self._get_duration_ms(),
            )

        max_chars = int(input_data.get("max_chars", 10000))
        pages_spec = input_data.get("pages", "")

        try:
            import pdfplumber

            with pdfplumber.open(str(path)) as pdf:
                total_pages = len(pdf.pages)
                target_pages = self._parse_pages(pages_spec, total_pages)

                texts = []
                for page_num in target_pages:
                    page = pdf.pages[page_num - 1]  # 1-indexed → 0-indexed
                    text = page.extract_text() or ""
                    texts.append(f"[페이지 {page_num}]\n{text}")

                full_text = "\n\n".join(texts)
                truncated = len(full_text) > max_chars
                if truncated:
                    full_text = full_text[:max_chars] + f"\n\n... (이하 생략, {len(full_text) - max_chars}자 초과)"

            return ToolResult(
                success=True,
                output={
                    "path": str(path),
                    "total_pages": total_pages,
                    "extracted_pages": target_pages,
                    "text": full_text,
                    "truncated": truncated,
                    "char_count": min(len(full_text), max_chars),
                },
                duration_ms=self._get_duration_ms(),
            )
        except Exception as e:
            logger.error(f"PDF 읽기 실패 ({path}): {e}")
            return ToolResult(
                success=False,
                output=None,
                error=str(e),
                duration_ms=self._get_duration_ms(),
            )

    def _parse_pages(self, spec: str, total: int) -> list[int]:
        """페이지 범위 파싱 (1-indexed)"""
        if not spec:
            return list(range(1, total + 1))

        pages = set()
        for part in spec.split(","):
            part = part.strip()
            if "-" in part:
                lo, hi = part.split("-", 1)
                lo_i = max(1, int(lo.strip()))
                hi_i = min(total, int(hi.strip()))
                pages.update(range(lo_i, hi_i + 1))
            elif part.isdigit():
                p = int(part)
                if 1 <= p <= total:
                    pages.add(p)

        return sorted(pages) if pages else list(range(1, total + 1))
