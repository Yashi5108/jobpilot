from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = Field(default="JobPilot", alias="APP_NAME")
    app_env: str = Field(default="development", alias="APP_ENV")
    database_url: str = Field(
        default="sqlite:///./data/jobpilot.db", alias="DATABASE_URL"
    )
    ollama_base_url: str = Field(
        default="http://localhost:11434", alias="OLLAMA_BASE_URL"
    )
    ollama_model: str = Field(default="llama3.1", alias="OLLAMA_MODEL")
    ollama_timeout_seconds: int = Field(
        default=60,
        alias="OLLAMA_TIMEOUT_SECONDS",
    )
    resume_storage_dir: str = Field(default="data/resumes", alias="RESUME_STORAGE_DIR")
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

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
