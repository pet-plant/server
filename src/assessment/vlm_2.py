from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

import torch
from transformers import AutoModelForImageTextToText, AutoProcessor

from assessment.aggregate import (
    AggregateError,
    aggregate_observations,
    assessment_output_timestamp,
    extract_json_object,
)
from assessment.probes_2 import DEFAULT_KNOWLEDGE_FILE, ProbeError, ProbePackage, build_probe_package

ASSESSMENT_DIR = Path(__file__).resolve().parent
DEFAULT_MODEL_PATH = ASSESSMENT_DIR / "models" / "internvl3_5-2b"


class VLMError(RuntimeError):
    """Error raised when the VLM cannot run a two-image probe package."""


@dataclass(frozen=True)
class VLMConfig:
    """Runtime settings for the local InternVL two-image runner."""

    model_path: Path = DEFAULT_MODEL_PATH
    max_new_tokens: int = 520
    temperature: float = 0.3

    @property
    def do_sample(self) -> bool:
        """Sampling is enabled only when temperature is greater than zero."""

        return self.temperature > 0


@dataclass(frozen=True)
class LoadedVLM:
    """Loaded processor and model pair."""

    processor: AutoProcessor
    model: AutoModelForImageTextToText


def load_vlm(config: VLMConfig) -> LoadedVLM:
    """Load the local InternVL processor and model."""

    if not config.model_path.exists():
        raise VLMError(f"Model path does not exist: {config.model_path}")

    print("Loading model...")
    processor = AutoProcessor.from_pretrained(
        str(config.model_path),
        trust_remote_code=True,
    )
    model = AutoModelForImageTextToText.from_pretrained(
        str(config.model_path),
        torch_dtype=torch.float16,
        device_map="auto",
        trust_remote_code=True,
    )
    print("Model loaded.")
    return LoadedVLM(processor=processor, model=model)


def input_device(model: AutoModelForImageTextToText) -> torch.device:
    """Return the device used for model input tensors."""

    return next(model.parameters()).device


def build_messages(package: ProbePackage) -> list[dict[str, object]]:
    """Build the two-image chat-template message payload expected by InternVL."""

    image_1_path = Path(package.image_1_path)
    image_2_path = Path(package.image_2_path)

    if not image_1_path.exists():
        raise VLMError(f"Image 1 does not exist: {image_1_path}")
    if not image_2_path.exists():
        raise VLMError(f"Image 2 does not exist: {image_2_path}")

    # The order here must match the prompt: first Image 1, then Image 2.
    return [
        {
            "role": "user",
            "content": [
                {"type": "image", "url": str(image_1_path)},
                {"type": "image", "url": str(image_2_path)},
                {"type": "text", "text": package.prompt},
            ],
        }
    ]


def run_probe_package(package: ProbePackage, loaded_vlm: LoadedVLM, config: VLMConfig) -> str:
    """Run one two-image probe package and return the raw decoded VLM response."""

    messages = build_messages(package)
    inputs = loaded_vlm.processor.apply_chat_template(
        messages,
        add_generation_prompt=True,
        tokenize=True,
        return_dict=True,
        return_tensors="pt",
    )

    device = input_device(loaded_vlm.model)
    inputs = {
        key: value.to(device) if torch.is_tensor(value) else value
        for key, value in inputs.items()
    }

    print("Running VLM...")
    generation_args = {
        "max_new_tokens": config.max_new_tokens,
        "do_sample": config.do_sample,
        "use_cache": True,
    }
    if config.do_sample:
        generation_args["temperature"] = config.temperature

    with torch.inference_mode():
        output_ids = loaded_vlm.model.generate(
            **inputs,
            **generation_args,
        )

    generated_ids = output_ids[:, inputs["input_ids"].shape[1] :]
    return loaded_vlm.processor.batch_decode(
        generated_ids,
        skip_special_tokens=True,
    )[0]


def image_ref(image_path: Path) -> str:
    """Format an image path as the file reference used in the final JSON output."""

    normalized = image_path.as_posix()
    if normalized.startswith("/"):
        return f"file://{normalized}"
    return f"file:///{normalized}"


def parse_args() -> argparse.Namespace:
    """Read command-line arguments for running one two-image VLM probe."""

    parser = argparse.ArgumentParser(description="Run one two-image VLM observation probe.")
    parser.add_argument("--probe", default="plant_observation_pair")
    parser.add_argument("--image-1", type=Path, required=True)
    parser.add_argument("--image-2", type=Path, required=True)
    parser.add_argument("--plant-id", default="plant_001")
    parser.add_argument("--model-path", type=Path, default=DEFAULT_MODEL_PATH)
    parser.add_argument("--max-new-tokens", type=int, default=520)
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--temperature", type=float, default=0.3)
    parser.add_argument("--show-runs", action="store_true")
    parser.add_argument("--knowledge-file", type=Path, default=DEFAULT_KNOWLEDGE_FILE)
    return parser.parse_args()


def main() -> int:
    """Entry point for `python -m assessment.vlm_2`."""

    args = parse_args()
    config = VLMConfig(
        model_path=args.model_path,
        max_new_tokens=args.max_new_tokens,
        temperature=args.temperature,
    )

    try:
        if args.runs < 1:
            raise VLMError("--runs must be at least 1.")
        if args.temperature < 0:
            raise VLMError("--temperature must be 0 or greater.")

        package = build_probe_package(
            args.probe,
            args.image_1,
            args.image_2,
            args.knowledge_file,
        )
        loaded_vlm = load_vlm(config)
        responses = []
        observations = []
        for run_index in range(args.runs):
            print(f"\n--- Run {run_index + 1}/{args.runs} ---")
            response = run_probe_package(package, loaded_vlm, config)
            responses.append(response)
            observations.append(extract_json_object(response))
        result = aggregate_observations(
            observations,
            plant_id=args.plant_id,
            species=package.species,
            timestamp=assessment_output_timestamp(args.image_2),
            image_refs=[image_ref(args.image_1), image_ref(args.image_2)],
        )
    except (ProbeError, VLMError, AggregateError) as error:
        print(f"VLM error: {error}")
        return 1

    if args.show_runs:
        print("\n============================")
        print("VLM OBSERVATION RUNS")
        print("============================")
        for run_index, response in enumerate(responses, start=1):
            print(f"\n--- RUN {run_index} RAW JSON ---")
            print(response)

    print()
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
