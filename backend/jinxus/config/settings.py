"""JINXUS 전체 설정 관리"""
from pydantic_settings import BaseSettings
from pydantic import Field
from functools import lru_cache
from pathlib import Path


class Settings(BaseSettings):
    """JINXUS 설정 - Pydantic BaseSettings로 환경변수 자동 로드"""

    # 버전
    jinxus_version: str = Field(default="1.6.0")

    # 서버
    jinxus_host: str = Field(default="0.0.0.0")
    jinxus_port: int = Field(default=19000)
    jinxus_debug: bool = Field(default=False)

    # LLM
    anthropic_api_key: str = Field(default="")
    claude_model: str = Field(default="claude-sonnet-4-6")
    claude_fallback_model: str = Field(default="claude-haiku-4-5-20251001")
    claude_fast_model: str = Field(default="claude-haiku-4-5-20251001")  # 분류/평가용 경량 모델

    # Redis (단기기억)
    redis_host: str = Field(default="localhost")
    redis_port: int = Field(default=16379)
    redis_password: str = Field(default="")

    # Qdrant (장기기억)
    qdrant_host: str = Field(default="localhost")
    qdrant_port: int = Field(default=16333)

    # OpenAI (임베딩)
    openai_api_key: str = Field(default="")
    gpt_emb_api_key: str = Field(default="")
    embedding_model: str = Field(default="text-embedding-3-small")
    embedding_dimensions: int = Field(default=1536)

    # SQLite (메타 저장)
    sqlite_path: str = Field(default="./data/jinxus_meta.db")

    # 도구
    tavily_api_key: str = Field(default="")
    naver_client_id: str = Field(default="")
    naver_client_secret: str = Field(default="")
    openweathermap_api_key: str = Field(default="")
    github_token: str = Field(default="")
    github_personal_access_token: str = Field(default="")

    # 텔레그램
    telegram_bot_token: str = Field(default="")
    telegram_authorized_user_id: int = Field(default=0)  # 허용된 사용자 ID

    # 자가 강화
    auto_improve_threshold: float = Field(default=0.6)
    reflect_every_n_tasks: int = Field(default=10)
    max_prompt_versions: int = Field(default=20)

    # MCP (Model Context Protocol)
    brave_api_key: str = Field(default="")  # Brave Search MCP용
    mcp_enabled: bool = Field(default=True)  # MCP 활성화 여부
    use_dynamic_tools: bool = Field(default=True)  # 에이전트 동적 도구 실행 (Claude tool_use)

    # Claude Code
    claude_code_storage: str = Field(default="./data/claude_sessions")
    claude_dangerously_skip_permissions: bool = Field(default=False)

    # 컨텍스트 관리
    max_output_chars: int = Field(default=4000)    # 에이전트 output 최대 길이
    max_context_chars: int = Field(default=8000)   # aggregate 최대 전체 길이

    # 모델 라우팅
    quality_critical_agents: list[str] = Field(default=["JX_WRITER", "JX_ANALYST"])
    complex_keywords: list[str] = Field(default=[
        "분석", "작성", "설계", "최적화", "자소서",
        "포트폴리오", "보고서", "논문", "리팩토링",
        "아키텍처", "시스템", "전략", "기획",
        "analyze", "design", "optimize", "architecture",
    ])
    simple_patterns: list[str] = Field(default=[
        "안녕", "뭐해", "hi", "hello", "네", "응", "ㅇㅇ", "고마워", "감사",
    ])

    # 작업 관리
    task_retention_hours: int = Field(default=1)
    max_tasks: int = Field(default=100)

    # 프로젝트 경로
    @property
    def project_root(self) -> Path:
        return Path(__file__).parent.parent

    @property
    def backend_root(self) -> Path:
        """backend 디렉토리 경로"""
        return Path(__file__).parent.parent.parent

    @property
    def prompts_dir(self) -> Path:
        return self.backend_root / "prompts"

    @property
    def data_dir(self) -> Path:
        return self.backend_root / "data"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore"
    }


@lru_cache()
def get_settings() -> Settings:
    """싱글톤 패턴으로 설정 객체 반환"""
    return Settings()
