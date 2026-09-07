"""Typed application configuration.

Field *values* are not hard-coded here — only their names and types. They are
read (each layer overriding the previous) from:

1. ``.env.example`` — committed defaults, the single source of default config;
2. ``.env`` — optional local overrides (git-ignored);
3. real environment variables — deployment / compose overrides.

Every context imports :func:`get_settings` rather than reading ``os.environ``.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

#: The repository root, derived from this file rather than from the working
#: directory. `src/core/config.py` -> `src/core` -> `src` -> the root; the same
#: two steps land on `/app` in the container image.
PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Absolute, so configuration does not depend on where a process happened
        # to be started. Relative paths here would resolve against the current
        # directory, which breaks every entry point that is not run from the
        # repository root — a cron job, an experiment CLI, a debugger.
        env_file=(PROJECT_ROOT / ".env.example", PROJECT_ROOT / ".env"),
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

    # --- external LLM (text only — never images; used by `mlops`) ---
    # Where to reach it and how to authenticate — deployment concerns. Which
    # model to run is not one of them: that belongs to the Langfuse prompt
    # version's `config`, so it is versioned with the text it was tuned against.
    llm_api_base: str = ""
    llm_api_key: str = ""

    # --- Langfuse (prompt management, tracing, datasets; used by `mlops`) ---
    # Langfuse is split by project, one per LLM-using component, so there is a
    # key pair per component rather than one for the server. Resolved by
    # `mlops.settings.credentials_for`.
    langfuse_host: str = ""
    langfuse_assessment_public_key: str = ""
    langfuse_assessment_secret_key: str = ""
    langfuse_advice_public_key: str = ""
    langfuse_advice_secret_key: str = ""
    langfuse_knowledge_public_key: str = ""
    langfuse_knowledge_secret_key: str = ""
    langfuse_registry_public_key: str = ""
    langfuse_registry_secret_key: str = ""


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings singleton."""
    # Values are supplied by the env-file / environment sources, not as
    # constructor arguments — hence the ignore for the "missing argument" check.
    return Settings()  # type: ignore[call-arg]
