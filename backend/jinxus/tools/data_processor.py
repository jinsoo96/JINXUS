"""DataProcessor - CSV/Excel/JSON 데이터 분석 도구

pandas 기반 데이터 처리:
- CSV/Excel 파일 읽기 및 분석
- 통계 요약 (describe)
- 필터링, 정렬, 그룹핑
- 데이터 변환 및 내보내기
"""
import json
import logging
from pathlib import Path
from typing import Any

from .base import JinxTool, ToolResult

logger = logging.getLogger(__name__)


class DataProcessor(JinxTool):
    """CSV/Excel/JSON 데이터 분석 도구"""

    name = "data_processor"
    description = "CSV, Excel, JSON 파일을 읽고 분석합니다. 통계 요약, 필터링, 정렬, 그룹핑 등 데이터 처리를 수행합니다."
    allowed_agents = ["JX_ANALYST", "JX_RESEARCHER", "JX_CODER", "JX_WRITER"]
    input_schema = {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["read", "describe", "filter", "query", "convert"],
                "description": "수행할 작업: read(파일 읽기), describe(통계 요약), filter(조건 필터링), query(SQL식 쿼리), convert(포맷 변환)",
            },
            "file_path": {
                "type": "string",
                "description": "분석할 파일 경로 (CSV, Excel, JSON)",
            },
            "query": {
                "type": "string",
                "description": "filter: pandas 조건식 (예: 'age > 30'), query: SQL식 쿼리",
            },
            "output_path": {
                "type": "string",
                "description": "convert 시 출력 파일 경로",
            },
            "limit": {
                "type": "integer",
                "description": "반환할 최대 행 수 (기본 20)",
                "default": 20,
            },
        },
        "required": ["action", "file_path"],
    }

    async def run(self, input_data: Any) -> ToolResult:
        try:
            import pandas as pd
        except ImportError:
            return ToolResult(success=False, output=None, error="pandas 패키지가 설치되지 않았습니다")

        if isinstance(input_data, str):
            input_data = json.loads(input_data)

        action = input_data.get("action", "read")
        file_path = input_data.get("file_path", "")
        query = input_data.get("query", "")
        output_path = input_data.get("output_path", "")
        limit = input_data.get("limit", 20)

        path = Path(file_path)
        if not path.exists():
            return ToolResult(success=False, output=None, error=f"파일을 찾을 수 없습니다: {file_path}")

        try:
            # 파일 읽기
            suffix = path.suffix.lower()
            if suffix == ".csv":
                df = pd.read_csv(path)
            elif suffix in (".xlsx", ".xls"):
                df = pd.read_excel(path)
            elif suffix == ".json":
                df = pd.read_json(path)
            else:
                return ToolResult(success=False, output=None, error=f"지원하지 않는 형식: {suffix}")

            if action == "read":
                result = f"파일: {path.name} ({len(df)}행 × {len(df.columns)}열)\n"
                result += f"컬럼: {', '.join(df.columns.tolist())}\n\n"
                result += df.head(limit).to_string(index=False)
                return ToolResult(success=True, output=result)

            elif action == "describe":
                desc = df.describe(include="all").to_string()
                info = f"파일: {path.name} ({len(df)}행 × {len(df.columns)}열)\n"
                info += f"컬럼: {', '.join(df.columns.tolist())}\n"
                info += f"결측치: {df.isnull().sum().to_dict()}\n\n"
                info += desc
                return ToolResult(success=True, output=info)

            elif action == "filter":
                if not query:
                    return ToolResult(success=False, output=None, error="filter 액션에는 query 파라미터가 필요합니다")
                filtered = df.query(query)
                result = f"필터 결과: {len(filtered)}행 (전체 {len(df)}행)\n\n"
                result += filtered.head(limit).to_string(index=False)
                return ToolResult(success=True, output=result)

            elif action == "query":
                if not query:
                    return ToolResult(success=False, output=None, error="query 파라미터가 필요합니다")
                result_df = df.query(query)
                result = f"쿼리 결과: {len(result_df)}행\n\n"
                result += result_df.head(limit).to_string(index=False)
                return ToolResult(success=True, output=result)

            elif action == "convert":
                if not output_path:
                    return ToolResult(success=False, output=None, error="convert에는 output_path가 필요합니다")
                out = Path(output_path)
                out.parent.mkdir(parents=True, exist_ok=True)
                out_suffix = out.suffix.lower()
                if out_suffix == ".csv":
                    df.to_csv(out, index=False)
                elif out_suffix in (".xlsx", ".xls"):
                    df.to_excel(out, index=False)
                elif out_suffix == ".json":
                    df.to_json(out, orient="records", force_ascii=False, indent=2)
                else:
                    return ToolResult(success=False, output=None, error=f"출력 형식 미지원: {out_suffix}")
                return ToolResult(success=True, output=f"변환 완료: {file_path} → {output_path} ({len(df)}행)")

            else:
                return ToolResult(success=False, output=None, error=f"알 수 없는 액션: {action}")

        except Exception as e:
            logger.error(f"[DataProcessor] 오류: {e}")
            return ToolResult(success=False, output=None, error=str(e))
