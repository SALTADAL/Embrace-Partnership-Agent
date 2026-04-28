"""Application configuration loaded from environment variables.

Uses Pydantic Settings so that values can be supplied via a ``.env`` file
or normal environment variables, with type validation built in. Every
import path in the app reaches its config through :func:`get_settings`,
which is cached so the file is read once per process.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Strongly-typed application settings.

    Attributes:
        anthropic_api_key: The Anthropic API key used by both agents.
            Required for live scoring; tests can run without it because
            the scoring service is dependency-injected.
        anthropic_model: Claude model identifier. Defaults to
            ``claude-sonnet-4-5`` per the project spec.
        database_url: SQLAlchemy URL for the SQLite database.
        research_timeout_seconds: Hard timeout for the research agent
            call. After this the service falls back to name-only scoring.
        scoring_timeout_seconds: Total budget for one scoring run.
        web_search_max_uses: Cap on how many ``web_search`` rounds the
            research agent may take per organization.
        log_level: Python logging level.
    """

    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-5"
    database_url: str = "sqlite:///./embrace.db"
    research_timeout_seconds: int = 30
    scoring_timeout_seconds: int = 60
    web_search_max_uses: int = 5
    log_level: str = "INFO"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached :class:`Settings` instance.

    The cache means repeated imports do not re-read ``.env`` from disk.
    Call :py:meth:`Settings.model_validate` directly in tests if you need
    a fresh instance with overrides.
    """

    return Settings()
