from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict
from pathlib import Path
from typing import Any

from capture.camera.config import CameraConfig


class VisionPipelineError(RuntimeError):
    """Error raised when the vision pipeline cannot complete."""


def camera_index_from_id(camera_id: str) -> int:
    """Convert a System Manager camera_id into the local OpenCV camera index."""

    normalized = camera_id.strip()
    if not normalized:
        raise VisionPipelineError("camera_id is required.")

    if normalized.isdigit():
        return int(normalized)

    match = re.search(r"(\d+)$", normalized)
    if match is None:
        raise VisionPipelineError(
            "camera_id must end with a numeric local camera index, "
            "for example 'webcam_0' or '0'."
        )
    return int(match.group(1))


def run_vision(
    camera_id: str,
    *,
    plant_id: str = "plant_001",
    raw_image_dir: str | Path = Path("images/raw"),
    processed_image_dir: str | Path = Path("images/processed"),
    fail_on_invalid_quality: bool = True,
    quality_config: Any | None = None,
    preprocess_config: Any | None = None,
) -> dict[str, Any]:
    """Capture one image, validate quality, preprocess it, and return JSON-ready data.

    This function is the System Manager-facing wrapper around the existing Vision PoC.
    `camera_id` identifies the local webcam and must contain the OpenCV index, such as
    `webcam_0` or `0`.
    """

    camera_index = camera_index_from_id(camera_id)
    raw_image_dir = Path(raw_image_dir)
    processed_image_dir = Path(processed_image_dir)

    try:
        from capture.camera.webcam import WebcamError, capture_once
        from capture.vision.preprocess import PreprocessConfig, PreprocessError, preprocess_image
        from capture.vision.quality import QualityConfig, QualityError, assess_image_quality

        capture_config = CameraConfig(
            plant_id=plant_id,
            camera_index=camera_index,
            raw_image_dir=raw_image_dir,
        )
        quality_config = quality_config or QualityConfig(min_blur_score=50.0)
        preprocess_config = preprocess_config or PreprocessConfig(output_dir=processed_image_dir)

        capture_metadata = capture_once(capture_config)
        raw_image_path = Path(capture_metadata.image_path)
        quality_result = assess_image_quality(raw_image_path, quality_config)

        if not quality_result.valid and fail_on_invalid_quality:
            return {
                "ok": False,
                "stage": "quality",
                "camera_id": camera_id,
                "plant_id": plant_id,
                "capture": asdict(capture_metadata),
                "quality": asdict(quality_result),
                "processed": None,
            }

        preprocess_metadata = preprocess_image(raw_image_path, preprocess_config)
    except (ImportError, RuntimeError) as error:
        raise VisionPipelineError(str(error)) from error

    return {
        "ok": True,
        "stage": "completed",
        "camera_id": camera_id,
        "plant_id": plant_id,
        "capture": asdict(capture_metadata),
        "quality": asdict(quality_result),
        "processed": asdict(preprocess_metadata),
    }


def parse_args() -> argparse.Namespace:
    """Read CLI arguments for manual vision-pipeline testing."""

    parser = argparse.ArgumentParser(description="Run the PoC vision pipeline once.")
    parser.add_argument("--camera-id", required=True)
    parser.add_argument("--plant-id", default="plant_001")
    parser.add_argument("--raw-image-dir", type=Path, default=Path("images/raw"))
    parser.add_argument("--processed-image-dir", type=Path, default=Path("images/processed"))
    parser.add_argument("--allow-invalid-quality", action="store_true")
    return parser.parse_args()


def main() -> int:
    """Entry point for `python -m capture.run_vision`."""

    args = parse_args()
    try:
        result = run_vision(
            args.camera_id,
            plant_id=args.plant_id,
            raw_image_dir=args.raw_image_dir,
            processed_image_dir=args.processed_image_dir,
            fail_on_invalid_quality=not args.allow_invalid_quality,
        )
    except VisionPipelineError as error:
        print(f"Vision pipeline error: {error}")
        return 1

    print(json.dumps(result, indent=2))
    return 0 if result["ok"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
