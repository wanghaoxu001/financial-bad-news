"""Configuration handling for the financial bad news project."""

from __future__ import annotations

from functools import lru_cache

from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration sourced from environment variables or .env file."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # TopHub configuration
    tophub_api_key: str | None = Field(default=None, validation_alias="TOPHUB_API_KEY")
    tophub_base_url: AnyHttpUrl = Field(
        default="https://api.tophubdata.com", validation_alias="TOPHUB_BASE_URL"
    )

    # LLM API integration
    llm_base_url: AnyHttpUrl = Field(validation_alias="LLM_BASE_URL")
    llm_api_key: str = Field(validation_alias="LLM_API_KEY")
    llm_model: str = Field(validation_alias="LLM_MODEL")

    # Application behaviour
    fetch_keyword: str = Field(default="银行", validation_alias="FETCH_KEYWORD")
    negative_keywords: str = Field(
        default="漏洞,信息泄露,网络安全,数据安全,诈骗,人脸,换脸,盗刷,信用卡,盗窃,欺诈",
        validation_alias="NEGATIVE_KEYWORDS",
        description="Comma separated keywords for initial filtering.",
    )
    page_size: int = Field(default=50, validation_alias="FETCH_PAGE_SIZE", ge=10, le=100)
    scheduler_interval_minutes: int = Field(
        default=30, validation_alias="SCHEDULER_INTERVAL_MINUTES", ge=5, le=720
    )
    sqlite_path: str = Field(default="data/news.db", validation_alias="SQLITE_PATH")

    # Classification thresholds
    sentiment_negative_threshold: float = Field(
        default=0.45,
        validation_alias="SENTIMENT_NEGATIVE_THRESHOLD",
        ge=0.0,
        le=1.0,
    )

    def keywords_list(self) -> list[str]:
        return [keyword.strip() for keyword in self.negative_keywords.split(",") if keyword.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[arg-type]


__all__ = ["Settings", "get_settings"]

