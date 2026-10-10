from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np


class AlignmentError(RuntimeError):
    """Error raised when comparison canvas generation fails."""


@dataclass(frozen=True)
class AlignmentConfig:
    """Settings for creating a labelled reference/current comparison canvas."""

    output_dir: Path = Path("images/processed")
    target_image_height: int = 1280
    label_height: int = 88
    padding: int = 24
    gap: int = 24
    background_color: tuple[int, int, int] = (245, 245, 245)
    panel_color: tuple[int, int, int] = (255, 255, 255)
    text_color: tuple[int, int, int] = (20, 20, 20)
    border_color: tuple[int, int, int] = (210, 210, 210)
    left_label: str = "A Healthy Reference"
    right_label: str = "B Current"


@dataclass(frozen=True)
class ImageShape:
    """Width and height for one image-like artifact."""

    width: int
    height: int


@dataclass(frozen=True)
class ComparisonMetadata:
    """Metadata written next to one comparison canvas."""

    reference_image_path: str
    current_image_path: str
    comparison_image_path: str
    canvas_type: str
    left_label: str
    right_label: str
    reference_shape: ImageShape
    current_shape: ImageShape
    canvas_shape: ImageShape


def load_image(image_path: Path) -> Any:
    """Load an image from disk and fail clearly if it cannot be read."""

    if not image_path.exists():
        raise AlignmentError(f"Image does not exist: {image_path}")

    image = cv2.imread(str(image_path))
    if image is None:
        raise AlignmentError(f"Could not load image: {image_path}")

    return image


def image_shape(image: Any) -> ImageShape:
    """Return image dimensions in metadata-friendly order."""

    height, width = image.shape[:2]
    return ImageShape(width=int(width), height=int(height))


def resize_to_height(image: Any, target_height: int) -> Any:
    """Resize an image to a target height while preserving aspect ratio."""

    height, width = image.shape[:2]
    if height == target_height:
        return image

    scale = target_height / float(height)
    output_size = (int(width * scale), target_height)
    return cv2.resize(image, output_size, interpolation=cv2.INTER_AREA)


def create_panel(image: Any, panel_width: int, panel_height: int, config: AlignmentConfig) -> Any:
    """Place an image on a fixed-size white panel without stretching it."""

    panel = np.full((panel_height, panel_width, 3), config.panel_color, dtype=np.uint8)
    image_height, image_width = image.shape[:2]
    x = (panel_width - image_width) // 2
    y = (panel_height - image_height) // 2
    panel[y : y + image_height, x : x + image_width] = image
    cv2.rectangle(panel, (0, 0), (panel_width - 1, panel_height - 1), config.border_color, 1)
    return panel


def draw_label(canvas: Any, label: str, x: int, y: int, config: AlignmentConfig) -> None:
    """Draw one label above a panel."""

    cv2.putText(
        canvas,
        label,
        (x, y),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.9,
        config.text_color,
        2,
        cv2.LINE_AA,
    )


def create_side_by_side_canvas(reference_image: Any, current_image: Any, config: AlignmentConfig) -> Any:
    """Create a single labelled canvas with reference on the left and current on the right."""

    reference_resized = resize_to_height(reference_image, config.target_image_height)
    current_resized = resize_to_height(current_image, config.target_image_height)

    ref_height, ref_width = reference_resized.shape[:2]
    cur_height, cur_width = current_resized.shape[:2]
    panel_width = max(ref_width, cur_width)
    panel_height = max(ref_height, cur_height)

    left_panel = create_panel(reference_resized, panel_width, panel_height, config)
    right_panel = create_panel(current_resized, panel_width, panel_height, config)

    canvas_width = (config.padding * 2) + (panel_width * 2) + config.gap
    canvas_height = (config.padding * 2) + config.label_height + panel_height
    canvas = np.full((canvas_height, canvas_width, 3), config.background_color, dtype=np.uint8)

    left_x = config.padding
    right_x = config.padding + panel_width + config.gap
    panel_y = config.padding + config.label_height
    label_y = config.padding + 48

    draw_label(canvas, config.left_label, left_x, label_y, config)
    draw_label(canvas, config.right_label, right_x, label_y, config)
    canvas[panel_y : panel_y + panel_height, left_x : left_x + panel_width] = left_panel
    canvas[panel_y : panel_y + panel_height, right_x : right_x + panel_width] = right_panel
    return canvas


def output_paths(current_image_path: Path, config: AlignmentConfig) -> tuple[Path, Path]:
    """Build output paths from the current image stem."""

    config.output_dir.mkdir(parents=True, exist_ok=True)
    stem = current_image_path.stem
    image_path = config.output_dir / f"{stem}_comparison.jpg"
    metadata_path = config.output_dir / f"{stem}_comparison.json"
    return image_path, metadata_path


def create_comparison_canvas(
    reference_image_path: Path,
    current_image_path: Path,
    config: AlignmentConfig,
) -> ComparisonMetadata:
    """Load reference/current images, create the canvas, and save image plus metadata."""

    reference_image = load_image(reference_image_path)
    current_image = load_image(current_image_path)
    canvas = create_side_by_side_canvas(reference_image, current_image, config)

    comparison_image_path, metadata_path = output_paths(current_image_path, config)
    if not cv2.imwrite(str(comparison_image_path), canvas):
        raise AlignmentError(f"Could not save comparison canvas to {comparison_image_path}.")

    metadata = ComparisonMetadata(
        reference_image_path=str(reference_image_path),
        current_image_path=str(current_image_path),
        comparison_image_path=str(comparison_image_path),
        canvas_type="side_by_side",
        left_label=config.left_label,
        right_label=config.right_label,
        reference_shape=image_shape(reference_image),
        current_shape=image_shape(current_image),
        canvas_shape=image_shape(canvas),
    )
    metadata_path.write_text(json.dumps(asdict(metadata), indent=2) + "\n", encoding="utf-8")
    return metadata


def parse_args() -> argparse.Namespace:
    """Read command-line arguments for comparison canvas generation."""

    parser = argparse.ArgumentParser(description="Create a labelled reference/current canvas.")
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--current", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("images/processed"))
    parser.add_argument("--target-image-height", type=int, default=1280)
    return parser.parse_args()


def main() -> int:
    """Entry point for `python -m capture.vision.alignment`."""

    args = parse_args()
    config = AlignmentConfig(
        output_dir=args.output_dir,
        target_image_height=args.target_image_height,
    )

    try:
        metadata = create_comparison_canvas(args.reference, args.current, config)
    except AlignmentError as error:
        print(f"Alignment error: {error}")
        return 1

    print(f"Comparison canvas: {metadata.comparison_image_path}")
    print(json.dumps(asdict(metadata), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
