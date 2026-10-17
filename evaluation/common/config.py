"""Configuration loader for the evaluation suite.

Model ids are not chosen here. Chat, embeddings, and the vision model come
from application settings (``.env``), including the OpenAI-to-Ollama fallback
when ``LLM_API_KEY`` is empty.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


@dataclass
class QualityThresholds:
    min_width: int = 640
    min_height: int = 480
    min_brightness: float = 40.0
    max_brightness: float = 220.0
    min_blur_score: float = 50.0


@dataclass
class LatencySLA:
    median_ms: int = 2500
    p95_ms: int = 6000


@dataclass
class EvaluationConfig:
    confidence_threshold: float = 0.5
    fast_mode: bool = False
    enable_judge: bool = False
    judge_provider: str = "openai"
    judge_model: str = ""
    reports_dir: Path = field(default_factory=lambda: PROJECT_ROOT / "evaluation" / "reports")
    keep_latest: bool = True
    quality_thresholds: QualityThresholds = field(default_factory=QualityThresholds)
    latency_sla: LatencySLA = field(default_factory=LatencySLA)
    ollama_host: str = "http://localhost:11434"
    #: Embedding model taken from settings. Empty until :meth:`load` resolves it.
    ollama_embed_model: str = ""
    embedding_provider: str = ""
    llm_min_similarity: float = 70.0
    llm_max_difference: float = 30.0
    llm_min_action_alignment: float = 80.0
    execution_mode: str = "in_memory"
    base_url: str = "http://localhost:8000"

    @classmethod
    def load(cls, config_path: Path | None = None) -> EvaluationConfig:
        """Load evaluation config from JSON, falling back to default.json."""
        if config_path is None:
            config_path = PROJECT_ROOT / "evaluation" / "config" / "default.json"

        raw: dict[str, Any] = {}
        if config_path.exists():
            with open(config_path, encoding="utf-8") as f:
                raw = json.load(f)

        q_raw = raw.get("quality_thresholds", {})
        quality_cfg = QualityThresholds(
            min_width=int(q_raw.get("min_width", 640)),
            min_height=int(q_raw.get("min_height", 480)),
            min_brightness=float(q_raw.get("min_brightness", 40.0)),
            max_brightness=float(q_raw.get("max_brightness", 220.0)),
            min_blur_score=float(q_raw.get("min_blur_score", 50.0)),
        )

        l_raw = raw.get("latency_sla", {})
        latency_cfg = LatencySLA(
            median_ms=int(l_raw.get("median_ms", 2500)),
            p95_ms=int(l_raw.get("p95_ms", 6000)),
        )

        reports_raw = raw.get("reports_dir", "evaluation/reports")
        reports_path = PROJECT_ROOT / reports_raw if not Path(reports_raw).is_absolute() else Path(reports_raw)

        config = cls(
            confidence_threshold=float(raw.get("confidence_threshold", 0.5)),
            fast_mode=bool(raw.get("fast_mode", False)),
            enable_judge=bool(raw.get("enable_judge", False)),
            judge_provider=str(raw.get("judge_provider", "openai")),
            judge_model="",
            reports_dir=reports_path,
            keep_latest=bool(raw.get("keep_latest", True)),
            quality_thresholds=quality_cfg,
            latency_sla=latency_cfg,
            ollama_host=str(raw.get("ollama_host", "http://localhost:11434")),
            llm_min_similarity=float(raw.get("llm_min_similarity", 70.0)),
            llm_max_difference=float(raw.get("llm_max_difference", 30.0)),
            llm_min_action_alignment=float(raw.get("llm_min_action_alignment", 80.0)),
            execution_mode=str(raw.get("execution_mode", "in_memory")),
            base_url=str(raw.get("base_url", "http://localhost:8000")),
        )
        return apply_runtime_models(config)


@dataclass(frozen=True)
class RuntimeModels:
    """The models the current settings will actually run."""

    llm_provider: str
    llm_model: str
    embedding_provider: str
    embedding_model: str
    embedding_host: str
    embedding_api_base: str
    embedding_api_key: str
    vlm_provider: str
    vlm_model: str


def runtime_models(settings: Any) -> RuntimeModels:
    """Resolve chat, embedding, and vision models from application settings.

    OpenAI is used only when its API key is set. Otherwise chat and embeddings
    delegate to Ollama. The embedding id is ``EMBEDDING_MODEL``; a blank
    ``EMBEDDING_PROVIDER`` follows ``LLM_PROVIDER`` before that fallback.
    """
    llm_provider = (getattr(settings, "llm_provider", "") or "openai").lower().strip()
    if llm_provider != "ollama" and not (getattr(settings, "llm_api_key", "") or "").strip():
        llm_provider = "ollama"
    llm_model = (
        getattr(settings, "ollama_model", "") or ""
        if llm_provider == "ollama"
        else getattr(settings, "llm_model", "") or ""
    )

    embedding_provider = (
        getattr(settings, "embedding_provider", "")
        or getattr(settings, "llm_provider", "")
        or "openai"
    ).lower().strip()
    if embedding_provider != "ollama" and not (getattr(settings, "llm_api_key", "") or "").strip():
        embedding_provider = "ollama"
    embedding_model = (getattr(settings, "embedding_model", "") or "").strip()
    if embedding_provider == "ollama":
        embedding_host = getattr(settings, "ollama_host", "") or "http://localhost:11434"
        embedding_api_base = ""
        embedding_api_key = ""
    else:
        embedding_host = ""
        embedding_api_base = getattr(settings, "llm_api_base", "") or ""
        embedding_api_key = getattr(settings, "llm_api_key", "") or ""

    vlm_provider = (getattr(settings, "vlm_provider", "") or "vllm").lower().strip()
    if vlm_provider == "local":
        vlm_model = getattr(settings, "vlm_local_model_path", "") or ""
    else:
        vlm_model = getattr(settings, "vlm_api_base", "") or ""

    return RuntimeModels(
        llm_provider=llm_provider,
        llm_model=llm_model,
        embedding_provider=embedding_provider,
        embedding_model=embedding_model,
        embedding_host=embedding_host,
        embedding_api_base=embedding_api_base,
        embedding_api_key=embedding_api_key,
        vlm_provider=vlm_provider,
        vlm_model=vlm_model,
    )


def apply_runtime_models(config: EvaluationConfig) -> EvaluationConfig:
    """Point this config at the models named by application settings."""
    try:
        from core.config import get_settings

        models = runtime_models(get_settings())
    except Exception:
        return config
    config.judge_provider = models.llm_provider
    config.judge_model = models.llm_model
    config.embedding_provider = models.embedding_provider
    config.ollama_embed_model = models.embedding_model
    if models.embedding_host:
        config.ollama_host = models.embedding_host
    return config
