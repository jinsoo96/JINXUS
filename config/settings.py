"""JINXUS 전체 설정 관리"""
from pydantic_settings import BaseSettings
from pydantic import Field
from functools import lru_cache
from pathlib import Path


class Settings(BaseSettings):
    """JINXUS 설정 - Pydantic BaseSettings로 환경변수 자동 로드"""

    # 서버
    jinxus_host: str = Field(default="0.0.0.0")
    jinxus_port: int = Field(default=9000)
    jinxus_debug: bool = Field(default=False)

    # LLM
    anthropic_api_key: str = Field(default="")
    claude_model: str = Field(default="claude-sonnet-4-20250514")
    claude_fallback_model: str = Field(default="claude-sonnet-4-20250514")

    # Redis (단기기억)
    redis_host: str = Field(default="localhost")
    redis_port: int = Field(default=6379)
    redis_password: str = Field(default="")

    # Qdrant (장기기억)
    qdrant_host: str = Field(default="localhost")
    qdrant_port: int = Field(default=6333)

    # OpenAI (임베딩)
    openai_api_key: str = Field(default="")
    gpt_emb_api_key: str = Field(default="")

    # SQLite (메타 저장)
    sqlite_path: str = Field(default="./data/jinxus_meta.db")

    # 도구
    tavily_api_key: str = Field(default="")
    github_token: str = Field(default="")
    github_personal_access_token: str = Field(default="")

    # 텔레그램
    telegram_bot_token: str = Field(default="")
    telegram_authorized_user_id: int = Field(default=0)  # 허용된 사용자 ID

    # 자가 강화
    auto_improve_threshold: float = Field(default=0.6)
    reflect_every_n_tasks: int = Field(default=10)
    max_prompt_versions: int = Field(default=20)

    # Claude Code
    claude_code_storage: str = Field(default="/tmp/jinxus_sessions")
    claude_dangerously_skip_permissions: bool = Field(default=True)

    # 프로젝트 경로
    @property
    def project_root(self) -> Path:
        return Path(__file__).parent.parent

    @property
    def prompts_dir(self) -> Path:
        return self.project_root / "prompts"

    @property
    def data_dir(self) -> Path:
        return self.project_root / "data"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore"
    }


@lru_cache()
def get_settings() -> Settings:
    """싱글톤 패턴으로 설정 객체 반환"""
    return Settings()
