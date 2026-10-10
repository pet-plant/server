from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import cv2


class PreprocessError(RuntimeError):
    """Error raised when an image cannot be preprocessed."""


@dataclass(frozen=True)
class PreprocessConfig:
    """Settings for the Phase 2 whole-plant preprocessing step."""

    output_dir: Path = Path("images/processed")
    crop_type: str = "whole_plant"
    crop_method: str = "green_mask_bbox"
    margin_ratio: float = 0.22
    bottom_margin_ratio: float = 0.35
    max_side: int = 1280
    min_mask_area_ratio: float = 0.01


@dataclass(frozen=True)
class CropBox:
    """Rectangle used to crop the raw image."""

    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True)
class PreprocessMetadata:
    """Metadata written for one processed whole-plant image."""

    source_image_path: str
    processed_image_path: str
    crop_type: str
    crop_method: str
    bbox: CropBox
    margin_ratio: float
    bottom_margin_ratio: float
    source_width: int
    source_height: int
    output_width: int
    output_height: int


def load_image(image_path: Path) -> Any:
    """Load a raw image from disk and fail clearly if it cannot be read."""

    if not image_path.exists():
        raise PreprocessError(f"Image does not exist: {image_path}")

    image = cv2.imread(str(image_path))
    if image is None:
        raise PreprocessError(f"Could not load image: {image_path}")

    return image


def build_green_mask(image: Any) -> Any:
    """Create a rough mask for green plant tissue using HSV color thresholds."""

    hsv_image = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    lower_green = (35, 25, 20)
    upper_green = (95, 255, 255)
    mask = cv2.inRange(hsv_image, lower_green, upper_green)

    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    return mask


def find_mask_bbox(mask: Any, config: PreprocessConfig) -> CropBox:
    """Find a bounding box around the detected plant mask."""

    image_height, image_width = mask.shape[:2]
    nonzero_pixels = cv2.findNonZero(mask)
    if nonzero_pixels is None:
        raise PreprocessError("Could not find green plant pixels in the image.")

    mask_area_ratio = len(nonzero_pixels) / float(image_width * image_height)
    if mask_area_ratio < config.min_mask_area_ratio:
        raise PreprocessError(
            f"Detected plant mask is too small: {mask_area_ratio:.4f}. "
            "Check lighting, framing, or mask thresholds."
        )

    x, y, width, height = cv2.boundingRect(nonzero_pixels)
    return CropBox(x=int(x), y=int(y), width=int(width), height=int(height))


def add_crop_margin(bbox: CropBox, image_width: int, image_height: int, config: PreprocessConfig) -> CropBox:
    """Expand the crop so leaves, pot rim, and nearby context are not cut off."""

    horizontal_margin = int(bbox.width * config.margin_ratio)
    top_margin = int(bbox.height * config.margin_ratio)
    bottom_margin = int(bbox.height * config.bottom_margin_ratio)

    x1 = max(0, bbox.x - horizontal_margin)
    y1 = max(0, bbox.y - top_margin)
    x2 = min(image_width, bbox.x + bbox.width + horizontal_margin)
    y2 = min(image_height, bbox.y + bbox.height + bottom_margin)

    return CropBox(x=x1, y=y1, width=x2 - x1, height=y2 - y1)


def crop_image(image: Any, bbox: CropBox) -> Any:
    """Crop the original image using the calculated crop box."""

    return image[bbox.y : bbox.y + bbox.height, bbox.x : bbox.x + bbox.width]


def resize_max_side(image: Any, max_side: int) -> Any:
    """Resize an image so its longest side is at most max_side."""

    height, width = image.shape[:2]
    longest_side = max(width, height)
    if longest_side <= max_side:
        return image

    scale = max_side / float(longest_side)
    output_size = (int(width * scale), int(height * scale))
    return cv2.resize(image, output_size, interpolation=cv2.INTER_AREA)


def output_paths(source_image_path: Path, config: PreprocessConfig) -> tuple[Path, Path]:
    """Build output paths for the processed image and metadata."""

    config.output_dir.mkdir(parents=True, exist_ok=True)
    stem = source_image_path.stem
    image_path = config.output_dir / f"{stem}_{config.crop_type}.jpg"
    metadata_path = config.output_dir / f"{stem}_{config.crop_type}.json"
    return image_path, metadata_path


def preprocess_image(source_image_path: Path, config: PreprocessConfig) -> PreprocessMetadata:
    """Create a whole-plant crop from a raw image and save the result."""

    source_image = load_image(source_image_path)
    source_height, source_width = source_image.shape[:2]

    mask = build_green_mask(source_image)
    mask_bbox = find_mask_bbox(mask, config)
    crop_bbox = add_crop_margin(mask_bbox, source_width, source_height, config)
    cropped_image = crop_image(source_image, crop_bbox)
    processed_image = resize_max_side(cropped_image, config.max_side)

    processed_image_path, metadata_path = output_paths(source_image_path, config)
    if not cv2.imwrite(str(processed_image_path), processed_image):
        raise PreprocessError(f"Could not save processed image to {processed_image_path}.")

    output_height, output_width = processed_image.shape[:2]
    metadata = PreprocessMetadata(
        source_image_path=str(source_image_path),
        processed_image_path=str(processed_image_path),
        crop_type=config.crop_type,
        crop_method=config.crop_method,
        bbox=crop_bbox,
        margin_ratio=config.margin_ratio,
        bottom_margin_ratio=config.bottom_margin_ratio,
        source_width=int(source_width),
        source_height=int(source_height),
        output_width=int(output_width),
        output_height=int(output_height),
    )
    metadata_path.write_text(json.dumps(asdict(metadata), indent=2) + "\n", encoding="utf-8")
    return metadata


def parse_args() -> argparse.Namespace:
    """Read command-line arguments for the preprocessing command."""

    parser = argparse.ArgumentParser(description="Preprocess one raw plant image.")
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("images/processed"))
    parser.add_argument("--margin-ratio", type=float, default=0.22)
    parser.add_argument("--bottom-margin-ratio", type=float, default=0.35)
    parser.add_argument("--max-side", type=int, default=1280)
    parser.add_argument("--min-mask-area-ratio", type=float, default=0.01)
    return parser.parse_args()


def main() -> int:
    """Entry point for `python -m capture.vision.preprocess`."""

    args = parse_args()
    config = PreprocessConfig(
        output_dir=args.output_dir,
        margin_ratio=args.margin_ratio,
        bottom_margin_ratio=args.bottom_margin_ratio,
        max_side=args.max_side,
        min_mask_area_ratio=args.min_mask_area_ratio,
    )

    try:
        metadata = preprocess_image(args.image, config)
    except PreprocessError as error:
        print(f"Preprocess error: {error}")
        return 1

    print(f"Processed image: {metadata.processed_image_path}")
    print(json.dumps(asdict(metadata), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
