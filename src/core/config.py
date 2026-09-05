"""Typed application configuration.

Field *values* are not hard-coded here — only their names and types. They are
read (each layer overriding the previous) from:

1. ``.env.example`` — committed defaults, the single source of default config;
2. ``.env`` — optional local overrides (git-ignored);
3. real environment variables — deployment / compose overrides.

Every context imports :func:`get_settings` rather than reading ``os.environ``.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env.example", ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- app ---
    app_env: str
    log_level: str

    # --- PostgreSQL ---
    database_url: str

    # --- MinIO / S3 (object storage; client lives in core.storage) ---
    minio_endpoint: str
    minio_access_key: str
    minio_secret_key: str
    minio_secure: bool
    minio_bucket_captures: str
    minio_bucket_frames_derived: str
    minio_bucket_exemplars: str
    minio_bucket_eval_sets: str

    # --- auth (OAuth2 / JWT, role-based) ---
    jwt_issuer: str
    jwt_audience: str
    jwt_alg: str
    jwt_secret: str
    access_token_ttl_seconds: int

    # --- auth: bootstrap admin (seeded on startup by core.users.ensure_admin_user) ---
    admin_email: str
    admin_name: str
    admin_password: str

    # --- ClearML (self-hosted; used by the mlops context) ---
    clearml_api_host: str = ""
    clearml_web_host: str = ""
    clearml_files_host: str = ""
    clearml_api_access_key: str = ""
    clearml_api_secret_key: str = ""


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    # Values are supplied by the env-file / environment sources, not as
    # constructor arguments — hence the ignore for the "missing argument" check.
    return Settings()  # type: ignore[call-arg]
