from __future__ import annotations

import argparse
import json
import platform
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import cv2
from capture.camera.config import CameraConfig

class WebcamError(RuntimeError):
    """Error raised for webcam-specific failures, such as open or read errors."""
    pass

@dataclass(frozen=True)
class CaptureMetadata:
    """Metadata written for one captured image."""

    plant_id: str
    camera_id: str
    captured_at: str
    image_path: str
    width: int
    height: int

def video_backend() -> int:
    """Choose the OpenCV video backend for the current operating system."""

    if platform.system() == "Windows":
        return cv2.CAP_DSHOW
    return cv2.CAP_ANY

def open_camera(camera_index: int) -> cv2.VideoCapture:
    """Open the webcam at the requested index, failing fast if unavailable."""

    camera = cv2.VideoCapture(camera_index, video_backend())
    if not camera.isOpened():
        camera.release()
        raise WebcamError(f"Could not open webcam at index {camera_index}.")
    return camera


def apply_camera_settings(camera: cv2.VideoCapture, config: CameraConfig) -> None:
    """Ask the webcam to use the configured capture resolution."""

    camera.set(cv2.CAP_PROP_FRAME_WIDTH, config.requested_width)
    camera.set(cv2.CAP_PROP_FRAME_HEIGHT, config.requested_height)


def detect_camera(config: CameraConfig) -> tuple[int, cv2.VideoCapture]:
    """Find the first webcam index that opens and returns a readable frame."""

    for camera_index in range(config.max_camera_index + 1):
        camera = cv2.VideoCapture(camera_index, video_backend())
        if not camera.isOpened():
            camera.release()
            continue

        apply_camera_settings(camera, config)

        success, frame = camera.read()
        if success and frame is not None:
            return camera_index, camera

        camera.release()

    raise WebcamError(
        "No readable webcam was found. Check that the USB webcam is connected "
        "and not already in use by another application."
    )


def ensure_output_dir(config: CameraConfig) -> Path:
    """Create the output directory for images and metadata if needed."""

    output_dir = config.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def capture_paths(output_dir: Path, captured_at: datetime) -> tuple[Path, Path]:
    """Build the image and metadata file paths from the capture timestamp."""

    filename_stem = captured_at.strftime("%Y-%m-%d_%H-%M-%S")
    return output_dir / f"{filename_stem}.jpg", output_dir / f"{filename_stem}.json"


def read_single_frame(camera: cv2.VideoCapture, warmup_frames: int) -> Any:
    """Read one frame after giving the camera a few frames to warm up."""

    frame = None
    attempts = max(1, warmup_frames + 1)

    for _ in range(attempts):
        success, current_frame = camera.read()
        if not success or current_frame is None:
            raise WebcamError("Could not read a frame from the webcam.")
        frame = current_frame

    return frame


def save_capture(
    frame: Any,
    *,
    config: CameraConfig,
    camera_index: int,
    captured_at: datetime | None = None,
) -> CaptureMetadata:
    """Save the captured frame as JPEG and write its JSON metadata."""

    captured_at = captured_at or datetime.now().astimezone()
    output_dir = ensure_output_dir(config)
    image_path, metadata_path = capture_paths(output_dir, captured_at)

    if not cv2.imwrite(str(image_path), frame):
        raise WebcamError(f"Could not save captured image to {image_path}.")

    height, width = frame.shape[:2]
    metadata = CaptureMetadata(
        plant_id=config.plant_id,
        camera_id=config.camera_id(camera_index),
        captured_at=captured_at.isoformat(timespec="seconds"),
        image_path=str(image_path),
        width=int(width),
        height=int(height),
    )
    metadata_path.write_text(json.dumps(asdict(metadata), indent=2) + "\n", encoding="utf-8")
    return metadata


def capture_once(config: CameraConfig) -> CaptureMetadata:
    """Open a webcam, capture one image, save it, and release the camera."""

    if config.camera_index is None:
        camera_index, camera = detect_camera(config)
    else:
        camera_index = config.camera_index
        camera = open_camera(camera_index)
        apply_camera_settings(camera, config)

    try:
        frame = read_single_frame(camera, config.warmup_frames)
        return save_capture(frame, config=config, camera_index=camera_index)
    finally:
        camera.release()


def parse_args() -> argparse.Namespace:
    """Read command-line arguments for the capture command."""

    parser = argparse.ArgumentParser(description="Capture one image from a USB webcam.")
    parser.add_argument("--plant-id", default="plant_001")
    parser.add_argument("--camera-index", type=int, default=None)
    parser.add_argument("--raw-image-dir", type=Path, default=Path("images/raw"))
    parser.add_argument("--max-camera-index", type=int, default=5)
    parser.add_argument("--warmup-frames", type=int, default=5)
    return parser.parse_args()


def main() -> int:
    """Entry point for `python -m capture.camera.webcam`."""

    args = parse_args()
    config = CameraConfig(
        plant_id=args.plant_id,
        camera_index=args.camera_index,
        raw_image_dir=args.raw_image_dir,
        max_camera_index=args.max_camera_index,
        warmup_frames=args.warmup_frames,
    )

    try:
        metadata = capture_once(config)
    except WebcamError as error:
        print(f"Webcam error: {error}")
        return 1

    print(f"Captured image: {metadata.image_path}")
    print("Metadata saved next to the image.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
