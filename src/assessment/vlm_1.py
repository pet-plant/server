from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import torch
from transformers import AutoModelForImageTextToText, AutoProcessor

from assessment.probes_1 import ProbeError, ProbePackage, build_probe_package

ASSESSMENT_DIR = Path(__file__).resolve().parent
DEFAULT_MODEL_PATH = ASSESSMENT_DIR / "models" / "internvl3_5-2b"


class VLMError(RuntimeError):
    """Error raised when the VLM cannot run a probe package."""


@dataclass(frozen=True)
class VLMConfig:
    """Runtime settings for the local InternVL probe runner."""

    model_path: Path = DEFAULT_MODEL_PATH
    max_new_tokens: int = 320
    do_sample: bool = False


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
    """Build the chat-template message payload expected by InternVL."""

    image_path = Path(package.image_path)
    if not image_path.exists():
        raise VLMError(f"Image does not exist: {image_path}")

    return [
        {
            "role": "user",
            "content": [
                {"type": "image", "url": str(image_path)},
                {"type": "text", "text": package.prompt},
            ],
        }
    ]


def run_probe_package(package: ProbePackage, loaded_vlm: LoadedVLM, config: VLMConfig) -> str:
    """Run one probe package and return the raw decoded VLM response."""

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
    with torch.inference_mode():
        output_ids = loaded_vlm.model.generate(
            **inputs,
            max_new_tokens=config.max_new_tokens,
            do_sample=config.do_sample,
            use_cache=True,
        )

    generated_ids = output_ids[:, inputs["input_ids"].shape[1] :]
    return loaded_vlm.processor.batch_decode(
        generated_ids,
        skip_special_tokens=True,
    )[0]


def parse_args() -> argparse.Namespace:
    """Read command-line arguments for running one assessment probe."""

    parser = argparse.ArgumentParser(description="Run one VLM assessment probe.")
    parser.add_argument("--probe", default="plant_observation")
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--model-path", type=Path, default=DEFAULT_MODEL_PATH)
    parser.add_argument("--max-new-tokens", type=int, default=320)
    return parser.parse_args()


def main() -> int:
    """Entry point for `python -m assessment.vlm`."""

    args = parse_args()
    config = VLMConfig(
        model_path=args.model_path,
        max_new_tokens=args.max_new_tokens,
    )

    try:
        package = build_probe_package(args.probe, args.image)
        loaded_vlm = load_vlm(config)
        response = run_probe_package(package, loaded_vlm, config)
    except (ProbeError, VLMError) as error:
        print(f"VLM error: {error}")
        return 1

    print("\n============================")
    print("VLM RESULT")
    print("============================")
    print(response)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

