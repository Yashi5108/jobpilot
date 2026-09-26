from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATABASE_URL = f"sqlite:///{(PROJECT_ROOT / 'data' / 'jobpilot.db').as_posix()}"
DEFAULT_RESUME_STORAGE_DIR = str(PROJECT_ROOT / "data" / "resumes")


class Settings(BaseSettings):
    app_name: str = Field(default="JobPilot", alias="APP_NAME")
    app_env: str = Field(default="development", alias="APP_ENV")
    database_url: str = Field(default=DEFAULT_DATABASE_URL, alias="DATABASE_URL")
    ollama_base_url: str = Field(
        default="http://localhost:11434", alias="OLLAMA_BASE_URL"
    )
    ollama_model: str = Field(default="llama3.1", alias="OLLAMA_MODEL")
    ollama_timeout_seconds: int = Field(
        default=60,
        alias="OLLAMA_TIMEOUT_SECONDS",
    )
    resume_storage_dir: str = Field(
        default=DEFAULT_RESUME_STORAGE_DIR,
        alias="RESUME_STORAGE_DIR",
    )
    resume_upload_max_bytes: int = Field(
        default=10 * 1024 * 1024,
        alias="RESUME_UPLOAD_MAX_BYTES",
    )
    browser_assistant_mode: str = Field(
        default="dry_run",
        alias="BROWSER_ASSISTANT_MODE",
    )
    browser_headless: bool = Field(
        default=True,
        alias="BROWSER_HEADLESS",
    )
    search_provider: str | None = Field(default=None, alias="SEARCH_PROVIDER")
    search_api_key: str | None = Field(default=None, alias="SEARCH_API_KEY")
    search_api_base_url: str | None = Field(
        default=None,
        alias="SEARCH_API_BASE_URL",
    )
    match_weight_required_skills: int = Field(
        default=50,
        alias="MATCH_WEIGHT_REQUIRED_SKILLS",
    )
    match_weight_preferred_skills: int = Field(
        default=15,
        alias="MATCH_WEIGHT_PREFERRED_SKILLS",
    )
    match_weight_experience: int = Field(
        default=20,
        alias="MATCH_WEIGHT_EXPERIENCE",
    )
    match_weight_education: int = Field(
        default=5,
        alias="MATCH_WEIGHT_EDUCATION",
    )
    match_weight_certification: int = Field(
        default=7,
        alias="MATCH_WEIGHT_CERTIFICATION",
    )
    match_weight_domain: int = Field(
        default=3,
        alias="MATCH_WEIGHT_DOMAIN",
    )

    @field_validator("database_url", mode="after")
    @classmethod
    def _normalize_database_url(cls, value: str) -> str:
        prefix = "sqlite:///"
        if not value.startswith(prefix):
            return value

        raw_path = value[len(prefix) :]
        if raw_path.startswith("/"):
            return value

        normalized_path = (PROJECT_ROOT / raw_path.removeprefix("./")).resolve()
        return f"{prefix}{normalized_path.as_posix()}"

    @field_validator("resume_storage_dir", mode="after")
    @classmethod
    def _normalize_resume_storage_dir(cls, value: str) -> str:
        path = Path(value)
        if path.is_absolute():
            return str(path)
        return str((PROJECT_ROOT / path).resolve())

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
