"""Where the VLM runs: in-process (transformers or MLX) or behind vLLM.

``VLM_PROVIDER`` picks one; both take the same prompt text and the two frames
and return the model's raw text, so :mod:`mlops.assessment.runtime` neither
knows nor cares which ran.

- ``local`` — in-process InternVL for laptops and development. The first probe
  picks CUDA when PyTorch can see a GPU, otherwise MLX on Apple Silicon when
  ``mlx-vlm`` and converted weights are present, otherwise CPU transformers.
  torch and transformers come from the opt-in ``vlm-local`` group
  (``uv sync --group vlm-local``); MLX from ``vlm-mlx``
  (``uv sync --group vlm-mlx``). Both are imported only when that runtime
  actually generates. If the configured weights directory has no model, that
  first load downloads ``OpenGVLab/InternVL3_5-2B-HF`` into it.
- ``vllm`` — :class:`VLLMBackend`, an OpenAI-compatible server at
  ``VLM_API_BASE``. For servers and production.
- ``http`` — :class:`GenerateAPIBackend`, a plain ``POST {VLM_API_BASE}/generate``
  server (e.g. a SageMaker host reached over Tailscale) that takes the prompt
  and base64 images as JSON and answers ``{"response": "..."}``.
"""

from __future__ import annotations

import base64
import logging
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from typing import Any, Protocol

import httpx
import openai
from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI

from core.config import get_settings

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]

#: Used when ``VLM_LOCAL_MODEL_PATH`` is blank.
DEFAULT_VLM_LOCAL_DIR = "models/internvl3_5-2b"
#: Hugging Face repo downloaded when that directory has no weights yet.
DEFAULT_VLM_REPO_ID = "OpenGVLab/InternVL3_5-2B-HF"


class VLMBackendUnavailableError(RuntimeError):
    """The backend cannot run at all: misconfigured, not installed or unreachable."""


class VLMBackend(Protocol):
    def generate(
        self,
        prompt: str,
        images: list[bytes],
        *,
        model: str,
        temperature: float,
        max_new_tokens: int,
    ) -> str:
        """Ask about ``images`` (JPEG bytes, in prompt order) and return the raw text."""
        ...


class LocalTransformersBackend:
    """InternVL in this process, loaded once per process from a local directory.

    The weights on disk *are* the model, so the ``model`` argument — the model id
    from the prompt config — is ignored here.
    """

    def __init__(self, model_path: str | Path) -> None:
        self.model_path = _resolve_model_path(model_path)

    def generate(
        self,
        prompt: str,
        images: list[bytes],
        *,
        model: str,
        temperature: float,
        max_new_tokens: int,
    ) -> str:
        try:
            import torch
            from PIL import Image
        except ImportError as error:
            raise VLMBackendUnavailableError(
                "VLM_PROVIDER=local needs the `vlm-local` dependency group: "
                "uv sync --group vlm-local"
            ) from error

        processor, vlm = _load_local_vlm(str(self.model_path))
        # The order here must match the prompt: first Image 1, then Image 2.
        messages = [
            {
                "role": "user",
                "content": [
                    *(
                        {"type": "image", "image": Image.open(BytesIO(data)).convert("RGB")}
                        for data in images
                    ),
                    {"type": "text", "text": prompt},
                ],
            }
        ]
        inputs = processor.apply_chat_template(
            messages,
            add_generation_prompt=True,
            tokenize=True,
            return_dict=True,
            return_tensors="pt",
        )

        device = next(vlm.parameters()).device
        inputs = {
            key: value.to(device) if torch.is_tensor(value) else value
            for key, value in inputs.items()
        }

        do_sample = temperature > 0
        generation_args: dict[str, Any] = {
            "max_new_tokens": max_new_tokens,
            "do_sample": do_sample,
            "use_cache": True,
        }
        if do_sample:
            generation_args["temperature"] = temperature

        with torch.inference_mode():
            output_ids = vlm.generate(**inputs, **generation_args)

        generated_ids = output_ids[:, inputs["input_ids"].shape[1] :]
        return str(processor.batch_decode(generated_ids, skip_special_tokens=True)[0])


@lru_cache(maxsize=1)
def _load_local_vlm(model_path: str) -> tuple[Any, Any]:
    """Load the InternVL processor and model once per process."""
    import torch
    from transformers import AutoModelForImageTextToText, AutoProcessor

    source = ensure_local_vlm(Path(model_path))
    # Use local_files_only=True when loading from an absolute path so that
    # transformers ≥5.x does not attempt to validate it as a HuggingFace repo ID.
    is_local = Path(source).is_absolute()
    processor = AutoProcessor.from_pretrained(
        source, trust_remote_code=True, local_files_only=is_local
    )
    use_cuda = torch.cuda.is_available()
    use_mps = not use_cuda and torch.backends.mps.is_available()
    dtype = torch.bfloat16 if use_cuda and torch.cuda.is_bf16_supported() else (
        torch.float16 if (use_cuda or use_mps) else torch.bfloat16
    )
    vlm = AutoModelForImageTextToText.from_pretrained(
        source,
        torch_dtype=dtype,
        device_map="auto" if use_cuda else None,
        low_cpu_mem_usage=True,
        trust_remote_code=True,
        local_files_only=is_local,
    )
    if use_mps:
        vlm = vlm.to("mps")
    return processor, vlm


def mlx_weights_path(hf_path: Path) -> Path:
    """Converted MLX weights sit beside the Hugging Face directory."""
    return hf_path.parent / f"{hf_path.name}-mlx"


class LocalMLXBackend:
    """InternVL through MLX on Apple Silicon.

    Weights are a one-time ``mlx_vlm.convert`` of the Hugging Face directory
    (``models/internvl3_5-2b-mlx``). If that load fails, the same call runs on
    the CPU transformers backend so the probe still completes.
    """

    def __init__(self, model_path: str | Path, cpu_model_path: str | Path) -> None:
        self.model_path = Path(model_path)
        self.cpu_model_path = Path(cpu_model_path)
        self._mlx_failed = False

    def generate(
        self,
        prompt: str,
        images: list[bytes],
        *,
        model: str,
        temperature: float,
        max_new_tokens: int,
    ) -> str:
        if not self._mlx_failed:
            try:
                return self._generate_mlx(
                    prompt,
                    images,
                    temperature=temperature,
                    max_new_tokens=max_new_tokens,
                )
            except Exception as error:  # noqa: BLE001 — any MLX load failure falls back to CPU
                self._mlx_failed = True
                logger.warning(
                    "MLX could not load %s (%s); using CPU",
                    self.model_path,
                    error,
                )
        return LocalTransformersBackend(self.cpu_model_path).generate(
            prompt,
            images,
            model=model,
            temperature=temperature,
            max_new_tokens=max_new_tokens,
        )

    def _generate_mlx(
        self,
        prompt: str,
        images: list[bytes],
        *,
        temperature: float,
        max_new_tokens: int,
    ) -> str:
        try:
            from mlx_vlm import generate
            from mlx_vlm.prompt_utils import apply_chat_template
        except ImportError as error:
            raise VLMBackendUnavailableError(
                "MLX needs the `vlm-mlx` dependency group: uv sync --group vlm-mlx"
            ) from error

        vlm, processor, config = _load_mlx_vlm(str(self.model_path))
        # The order here must match the prompt: first Image 1, then Image 2.
        image_inputs = [_jpeg_data_uri(data) for data in images]
        formatted = apply_chat_template(
            processor,
            config,
            prompt,
            num_images=len(image_inputs),
        )
        result = generate(
            vlm,
            processor,
            formatted,
            image=image_inputs or None,
            max_tokens=max_new_tokens,
            temperature=temperature,
            verbose=False,
        )
        text = getattr(result, "text", result)
        return str(text)


@lru_cache(maxsize=1)
def _load_mlx_vlm(model_path: str) -> tuple[Any, Any, Any]:
    """Load the MLX model, processor and config once per process."""
    from mlx_vlm import load
    from mlx_vlm.utils import load_config

    if not Path(model_path).is_dir():
        raise VLMBackendUnavailableError(f"MLX model path does not exist: {model_path}")
    model, processor = load(model_path)
    return model, processor, load_config(model_path)


def _jpeg_data_uri(data: bytes) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(data).decode("ascii")


def _resolve_model_path(model_path: str | Path) -> Path:
    raw = str(model_path).strip() or DEFAULT_VLM_LOCAL_DIR
    path = Path(raw)
    return path if path.is_absolute() else REPO_ROOT / path


def _weights_ready(path: Path) -> bool:
    """True only when the directory contains config.json *and* at least one weight file."""
    if not (path / "config.json").is_file():
        return False
    # Require actual weight shards — a directory with only tokenizer / processor
    # files (e.g. a partial snapshot_download) is not usable for inference.
    return any(path.glob("*.safetensors")) or any(path.glob("*.bin"))


def _directory_writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write_probe"
        probe.write_text("")
        probe.unlink()
    except OSError:
        return False
    return True


def _snapshot_download(repo_id: str, local_dir: str) -> None:
    try:
        from huggingface_hub import snapshot_download
    except ImportError as error:
        raise VLMBackendUnavailableError(
            "Downloading the default VLM needs the `vlm-local` dependency group: "
            "uv sync --group vlm-local"
        ) from error
    try:
        snapshot_download(repo_id=repo_id, local_dir=local_dir)
    except Exception as error:  # noqa: BLE001 — hub errors become one backend error
        raise VLMBackendUnavailableError(
            f"Could not download {repo_id} into {local_dir}: {error}"
        ) from error


def ensure_local_vlm(model_path: Path) -> str:
    """Return a weights directory, downloading the default Hugging Face model if needed.

    A directory that already contains ``config.json`` is used as-is. Otherwise
    ``OpenGVLab/InternVL3_5-2B-HF`` is saved into ``model_path``. When that
    directory cannot be written, the same repo id is returned so transformers
    loads it from the Hugging Face cache.
    """
    if _weights_ready(model_path):
        return str(model_path)
    if _directory_writable(model_path):
        logger.info(
            "No VLM weights at %s; downloading %s",
            model_path,
            DEFAULT_VLM_REPO_ID,
        )
        _snapshot_download(DEFAULT_VLM_REPO_ID, str(model_path))
        if not _weights_ready(model_path):
            raise VLMBackendUnavailableError(
                f"Downloaded {DEFAULT_VLM_REPO_ID} but {model_path} has no config.json"
            )
        return str(model_path)
    logger.info(
        "No writable VLM weights at %s; loading %s",
        model_path,
        DEFAULT_VLM_REPO_ID,
    )
    return DEFAULT_VLM_REPO_ID


def _cuda_available() -> bool:
    try:
        import torch
    except ImportError:
        return False
    return bool(torch.cuda.is_available())


def _mlx_metal_available() -> bool:
    try:
        import mlx.core as mx
    except ImportError:
        return False
    try:
        return bool(mx.metal.is_available())
    except (AttributeError, RuntimeError):
        return False


def _mps_available() -> bool:
    try:
        import torch
    except ImportError:
        return False
    return bool(torch.backends.mps.is_available())


def _select_local_backend(model_path: str | Path) -> VLMBackend:
    """CUDA, then MLX on Apple Silicon, then MPS (Apple Silicon GPU), then CPU transformers."""
    hf_path = _resolve_model_path(model_path)
    if _cuda_available():
        logger.info("local VLM runtime: cuda (%s)", hf_path)
        return LocalTransformersBackend(hf_path)
    mlx_path = mlx_weights_path(hf_path)
    if _mlx_metal_available() and mlx_path.is_dir():
        logger.info("local VLM runtime: mlx (%s)", mlx_path)
        return LocalMLXBackend(mlx_path, hf_path)
    if _mlx_metal_available():
        runtime_name = "mps" if _mps_available() else "cpu"
        logger.info("local VLM runtime: %s; MLX weights not found at %s", runtime_name, mlx_path)
    elif _mps_available():
        logger.info("local VLM runtime: mps (Apple Silicon GPU) (%s)", hf_path)
    else:
        logger.info("local VLM runtime: cpu (%s)", hf_path)
    return LocalTransformersBackend(hf_path)


class VLLMBackend:
    """An OpenAI-compatible VLM server (vLLM), images sent as base64 data URLs."""

    def __init__(self, api_base: str, api_key: str = "") -> None:
        self.api_base = api_base
        self.api_key = api_key

    def generate(
        self,
        prompt: str,
        images: list[bytes],
        *,
        model: str,
        temperature: float,
        max_new_tokens: int,
    ) -> str:
        chat = ChatOpenAI(
            base_url=self.api_base,
            model=model,
            temperature=temperature,
            max_completion_tokens=max_new_tokens,
            # vLLM accepts any key unless started with --api-key; the client
            # still insists on one being present.
            api_key=self.api_key or "unused",  # type: ignore[arg-type]
        )
        message = HumanMessage(
            content=[
                *(
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": "data:image/jpeg;base64,"
                            + base64.b64encode(data).decode("ascii")
                        },
                    }
                    for data in images
                ),
                {"type": "text", "text": prompt},
            ]
        )
        try:
            response = chat.invoke([message])
        except (openai.APIConnectionError, openai.APIStatusError) as error:
            raise VLMBackendUnavailableError(
                f"VLM server at {self.api_base} failed: {error}"
            ) from error
        content = response.content
        if isinstance(content, str):
            return content
        return "".join(
            part.get("text", "") if isinstance(part, dict) else str(part)
            for part in content
        )


class GenerateAPIBackend:
    """A ``POST /generate`` server: JSON in, ``{"response": text}`` out.

    Request body: ``prompt``, ``images_base64`` (JPEGs in prompt order: previous
    then current), and ``model`` / ``temperature`` / ``max_new_tokens``, which
    the server may honour or ignore. ``VLM_API_KEY``, when set, goes out as a
    bearer token.
    """

    def __init__(self, api_base: str, api_key: str = "", timeout: float = 120.0) -> None:
        self.url = api_base.rstrip("/") + "/generate"
        self.api_key = api_key
        self.timeout = timeout

    def generate(
        self,
        prompt: str,
        images: list[bytes],
        *,
        model: str,
        temperature: float,
        max_new_tokens: int,
    ) -> str:
        payload = {
            "prompt": prompt,
            "images_base64": [base64.b64encode(data).decode("ascii") for data in images],
            "model": model,
            "temperature": temperature,
            "max_new_tokens": max_new_tokens,
        }
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        try:
            response = httpx.post(self.url, json=payload, headers=headers, timeout=self.timeout)
            response.raise_for_status()
            text = response.json()["response"]
        except httpx.HTTPError as error:
            raise VLMBackendUnavailableError(f"VLM server at {self.url} failed: {error}") from error
        except (ValueError, KeyError, TypeError) as error:
            raise VLMBackendUnavailableError(
                f"VLM server at {self.url} returned no 'response' field: {error}"
            ) from error
        if not isinstance(text, str):
            raise VLMBackendUnavailableError(
                f"VLM server at {self.url} returned a non-text response"
            )
        return text


def get_vlm_backend() -> VLMBackend:
    """The backend ``VLM_PROVIDER`` names."""
    settings = get_settings()
    provider = (settings.vlm_provider or "").strip().lower()
    if provider == "local":
        return _select_local_backend(settings.vlm_local_model_path)
    if provider in ("vllm", "http"):
        if not settings.vlm_api_base:
            raise VLMBackendUnavailableError(f"VLM_PROVIDER={provider} but VLM_API_BASE is not set")
        if provider == "http":
            return GenerateAPIBackend(
                settings.vlm_api_base, settings.vlm_api_key, settings.vlm_api_timeout_seconds
            )
        return VLLMBackend(settings.vlm_api_base, settings.vlm_api_key)
    raise VLMBackendUnavailableError(
        f"unknown VLM_PROVIDER {settings.vlm_provider!r}; expected 'local', 'vllm' or 'http'"
    )
