from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CameraConfig:
    plant_id: str = "plant_001"
    camera_index: int | None = None
    camera_id_prefix: str = "webcam"
    raw_image_dir: Path = Path("images/raw")
    max_camera_index: int = 5
    warmup_frames: int = 5
    requested_width: int = 1280
    requested_height: int = 720

    @property
    def output_dir(self) -> Path:
        return self.raw_image_dir

    def camera_id(self, camera_index: int) -> str:
        return f"{self.camera_id_prefix}_{camera_index}"
