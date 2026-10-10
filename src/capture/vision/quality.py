from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import cv2


class QualityError(RuntimeError):
    """Error raised when an image cannot be loaded or assessed."""


@dataclass(frozen=True)
class QualityConfig:
    """Thresholds used to decide whether an image is good enough for the PoC."""

    min_width: int = 640
    min_height: int = 480
    min_brightness: float = 40.0
    max_brightness: float = 220.0
    min_blur_score: float = 100.0


@dataclass(frozen=True)
class QualityResult:
    """Image quality report for one input image."""

    valid: bool
    image_path: str
    width: int
    height: int
    brightness: float
    blur_score: float
    reasons: list[str]


def load_image(image_path: Path) -> Any:
    """Load an image from disk and fail clearly if it cannot be read."""

    if not image_path.exists():
        raise QualityError(f"Image does not exist: {image_path}")

    image = cv2.imread(str(image_path))
    if image is None:
        raise QualityError(f"Could not load image: {image_path}")

    return image


def check_resolution(width: int, height: int, config: QualityConfig) -> list[str]:
    """Check whether the image dimensions meet the minimum PoC resolution."""

    reasons: list[str] = []
    if width < config.min_width:
        reasons.append("image_too_narrow")
    if height < config.min_height:
        reasons.append("image_too_short")
    return reasons


def measure_brightness(gray_image: Any) -> float:
    """Measure average grayscale brightness from 0 to 255."""

    return float(gray_image.mean())


def check_brightness(brightness: float, config: QualityConfig) -> list[str]:
    """Check whether the image is too dark or too bright."""

    if brightness < config.min_brightness:
        return ["image_too_dark"]
    if brightness > config.max_brightness:
        return ["image_too_bright"]
    return []


def measure_blur(gray_image: Any) -> float:
    """Estimate sharpness with Laplacian variance; higher means sharper."""

    return float(cv2.Laplacian(gray_image, cv2.CV_64F).var())


def check_blur(blur_score: float, config: QualityConfig) -> list[str]:
    """Check whether the image appears too blurry for downstream vision work."""

    if blur_score < config.min_blur_score:
        return ["image_too_blurry"]
    return []


def assess_image_quality(image_path: Path, config: QualityConfig) -> QualityResult:
    """Run all PoC quality checks for one image."""

    image = load_image(image_path)
    height, width = image.shape[:2]
    gray_image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    brightness = measure_brightness(gray_image)
    blur_score = measure_blur(gray_image)

    reasons: list[str] = []
    reasons.extend(check_resolution(width, height, config))
    reasons.extend(check_brightness(brightness, config))
    reasons.extend(check_blur(blur_score, config))

    return QualityResult(
        valid=len(reasons) == 0,
        image_path=str(image_path),
        width=int(width),
        height=int(height),
        brightness=round(brightness, 2),
        blur_score=round(blur_score, 2),
        reasons=reasons,
    )


def parse_args() -> argparse.Namespace:
    """Read command-line arguments for the quality checker."""

    parser = argparse.ArgumentParser(description="Assess image quality for the Pet-Plant PoC.")
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--min-width", type=int, default=640)
    parser.add_argument("--min-height", type=int, default=480)
    parser.add_argument("--min-brightness", type=float, default=40.0)
    parser.add_argument("--max-brightness", type=float, default=220.0)
    parser.add_argument("--min-blur-score", type=float, default=50.0)
    return parser.parse_args()


def main() -> int:
    """Entry point for `python -m capture.vision.quality`."""

    args = parse_args()
    config = QualityConfig(
        min_width=args.min_width,
        min_height=args.min_height,
        min_brightness=args.min_brightness,
        max_brightness=args.max_brightness,
        min_blur_score=args.min_blur_score,
    )

    try:
        result = assess_image_quality(args.image, config)
    except QualityError as error:
        print(f"Quality error: {error}")
        return 1

    print(json.dumps(asdict(result), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
