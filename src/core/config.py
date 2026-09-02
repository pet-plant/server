"""Typed application configuration, loaded once from the environment.

Every context imports :func:`get_settings` rather than reading ``os.environ``
directly. Variable names mirror ``.env.example`` (owned by ``core``).
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- app ---
    app_env: str = "local"
    log_level: str = "INFO"

    # --- PostgreSQL ---
    database_url: str = "postgresql+psycopg://petplant:petplant@localhost:5432/petplant"

    # --- auth (OAuth2 / JWT, role-based) ---
    jwt_issuer: str = "pet-plant"
    jwt_audience: str = "pet-plant-api"
    jwt_alg: str = "HS256"
    jwt_secret: str = "change-me"
    access_token_ttl_seconds: int = 3600


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    return Settings()
