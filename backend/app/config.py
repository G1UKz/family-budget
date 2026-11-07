from datetime import date
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="BUDGET_", extra="ignore")

    database_url: str = "postgresql+psycopg://budget:budget@localhost:5432/budget"
    env: str = "dev"  # dev | prod
    secret_key: str = "dev-insecure-change-me"  # noqa: S105  (refused outside dev, see main.py)
    # Budget is counted by operation date starting from this day.
    start_date: date = date(2026, 6, 1)
    # Regex of "home" cities: purchases outside them during a trip go to the trip category.
    home_city_regex: str = r"(?i)hometown"  # задаётся через BUDGET_HOME_CITY_REGEX
    cookie_secure: bool = False
    static_dir: str = "static"  # built SPA; relative to the working directory
    session_max_age: int = 60 * 60 * 24 * 14

    # LLM suggestions (optional: without a key the review queue works without AI hints).
    anthropic_api_key: str | None = None
    llm_model: str = "claude-opus-5-5"
    llm_effort: str = "low"

    @field_validator("database_url")
    @classmethod
    def _driver(cls, v: str) -> str:
        # CloudNativePG publishes plain postgresql:// URIs; use the psycopg 3 driver.
        for prefix in ("postgresql://", "postgres://"):
            if v.startswith(prefix):
                return "postgresql+psycopg://" + v[len(prefix) :]
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
