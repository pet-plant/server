"""Unified HTTP Client adapter for evaluation against Pet-Plant FastAPI endpoints.

Supports:
1. Live running server (e.g. http://localhost:8000).
2. In-process ASGI transport via FastAPI application for headless CI.
"""

from __future__ import annotations

import io
import time
import uuid
from pathlib import Path
from typing import Any

import httpx

from core.config import get_settings


class EvaluationHttpClient:
    """HTTP client wrapper managing auth, device pairing, photo upload, and polling."""

    def __init__(self, base_url: str = "http://localhost:8000", app: Any | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        # Tracks every HTTP call: list of {"method": str, "path": str, "status": int}
        self.call_log: list[dict[str, Any]] = []
        if app is not None:
            # In-process synchronous FastAPI TestClient
            from fastapi.testclient import TestClient

            self.client = TestClient(app, base_url=self.base_url)
            self.is_in_process = True
        else:
            # Live server connection
            self.client = httpx.Client(base_url=self.base_url, timeout=30.0)
            self.is_in_process = False

    def _record(self, method: str, path: str, status_code: int) -> None:
        """Record a single HTTP call to the call log."""
        # Normalise dynamic path segments so /runs/abc and /runs/xyz both collapse
        import re
        normalised = re.sub(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
            "{id}",
            path,
        )
        self.call_log.append({"method": method, "path": normalised, "status": status_code})

    def get_endpoint_summary(self) -> list[dict[str, Any]]:
        """Return deduped endpoint list with call counts, sorted by method then path."""
        counts: dict[tuple[str, str], int] = {}
        for entry in self.call_log:
            key = (entry["method"], entry["path"])
            counts[key] = counts.get(key, 0) + 1
        return [
            {"method": method, "path": path, "calls": count, "source": "http"}
            for (method, path), count in sorted(counts.items())
        ]

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> EvaluationHttpClient:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        self.close()

    # --- 1. Health ---

    def check_health(self) -> bool:
        """Verify server is responding."""
        try:
            resp = self.client.get("/health")
            self._record("GET", "/health", resp.status_code)
            return resp.status_code == 200
        except Exception:
            return False

    # --- 2. Auth & Pairing ---

    def register_user(self, email: str, password: str, name: str = "Test User") -> dict[str, Any]:
        """Register a new user account."""
        resp = self.client.post(
            "/auth/register",
            json={"email": email, "password": password, "name": name},
        )
        self._record("POST", "/auth/register", resp.status_code)
        if resp.status_code in (200, 201):
            return resp.json()
        if resp.status_code == 409:
            return {"detail": "User already exists", "email": email}
        resp.raise_for_status()
        return resp.json()

    def login_user(self, email: str, password: str) -> str:
        """Authenticate user and return JWT access token."""
        resp = self.client.post(
            "/auth/token",
            data={"username": email, "password": password},
        )
        self._record("POST", "/auth/token", resp.status_code)
        resp.raise_for_status()
        data = resp.json()
        return data["access_token"]

    def login_admin(self) -> str:
        """Authenticate as bootstrap admin and return JWT access token."""
        settings = get_settings()
        return self.login_user(settings.admin_email, settings.admin_password)

    def start_device_pairing(self, physical_id: str) -> dict[str, str]:
        """Initiate device pairing flow."""
        resp = self.client.post("/devices/pair", json={"physical_id": physical_id})
        self._record("POST", "/devices/pair", resp.status_code)
        resp.raise_for_status()
        data = resp.json()
        return {
            "device_code": data["device_code"],
            "user_code": data["user_code"],
        }

    def approve_device_pairing(self, user_token: str, user_code: str, name: str = "Planter") -> dict[str, Any]:
        """Approve device pairing using user JWT."""
        resp = self.client.post(
            "/devices/pair/approve",
            headers={"Authorization": f"Bearer {user_token}"},
            json={"user_code": user_code, "name": name},
        )
        self._record("POST", "/devices/pair/approve", resp.status_code)
        resp.raise_for_status()
        return resp.json()

    def exchange_device_token(self, device_code: str) -> str:
        """Exchange device_code for long-lived device token (ppd_...)."""
        resp = self.client.post("/devices/pair/token", json={"device_code": device_code})
        self._record("POST", "/devices/pair/token", resp.status_code)
        resp.raise_for_status()
        data = resp.json()
        return data["access_token"]

    # --- 3. Plant Registry ---

    def register_plant(
        self,
        user_token: str,
        name: str,
        species_code: str,
        device_id: str | None = None,
    ) -> dict[str, Any]:
        """Register a plant bound to a device."""
        resp = self.client.post(
            "/registry/plants",
            headers={"Authorization": f"Bearer {user_token}"},
            json={"name": name, "species_code": species_code, "device_id": device_id},
        )
        self._record("POST", "/registry/plants", resp.status_code)
        if resp.status_code == 201:
            return resp.json()
        if resp.status_code == 409:
            # Device already bound or plant already exists
            return resp.json()
        resp.raise_for_status()
        return resp.json()

    # --- 4. Photo Capture Upload ---

    def upload_device_frame(
        self,
        device_token: str,
        image_path_or_bytes: Path | str | bytes,
    ) -> dict[str, Any]:
        """Upload a photo frame using edge device token."""
        if isinstance(image_path_or_bytes, (str, Path)):
            with open(image_path_or_bytes, "rb") as f:
                content = f.read()
        else:
            content = image_path_or_bytes

        files = {"image": ("frame.jpg", content, "image/jpeg")}
        resp = self.client.post(
            "/capture/devices/me/frames",
            headers={"Authorization": f"Bearer {device_token}"},
            files=files,
        )
        self._record("POST", "/capture/devices/me/frames", resp.status_code)
        resp.raise_for_status()
        return resp.json()

    def upload_plant_frame(
        self,
        superuser_token: str,
        plant_id: str | uuid.UUID,
        image_path_or_bytes: Path | str | bytes,
    ) -> dict[str, Any]:
        """Upload a photo frame for a plant by hand using admin credentials."""
        if isinstance(image_path_or_bytes, (str, Path)):
            with open(image_path_or_bytes, "rb") as f:
                content = f.read()
        else:
            content = image_path_or_bytes

        files = {"image": ("frame.jpg", content, "image/jpeg")}
        resp = self.client.post(
            f"/capture/plants/{plant_id}/frames",
            headers={"Authorization": f"Bearer {superuser_token}"},
            files=files,
        )
        self._record("POST", "/capture/plants/{id}/frames", resp.status_code)
        resp.raise_for_status()
        return resp.json()

    # --- 5. Orchestrator Runs ---

    def trigger_run(self, superuser_token: str, plant_id: str | uuid.UUID) -> dict[str, Any]:
        """Trigger an orchestrator run outside schedule."""
        resp = self.client.post(
            "/orchestrator/runs",
            headers={"Authorization": f"Bearer {superuser_token}"},
            json={"plant_id": str(plant_id)},
        )
        self._record("POST", "/orchestrator/runs", resp.status_code)
        resp.raise_for_status()
        return resp.json()

    def poll_run(
        self,
        superuser_token: str,
        run_id: str | uuid.UUID,
        timeout_seconds: float = 30.0,
        interval_seconds: float = 0.5,
    ) -> dict[str, Any]:
        """Poll orchestrator run status until succeeded or failed."""
        start = time.perf_counter()
        while time.perf_counter() - start < timeout_seconds:
            resp = self.client.get(
                f"/orchestrator/runs/{run_id}",
                headers={"Authorization": f"Bearer {superuser_token}"},
            )
            self._record("GET", "/orchestrator/runs/{id}", resp.status_code)
            resp.raise_for_status()
            data = resp.json()
            if data.get("status") in ("succeeded", "failed", "skipped"):
                return data
            time.sleep(interval_seconds)

        raise TimeoutError(f"Orchestrator run {run_id} timed out after {timeout_seconds}s")

    # --- 6. Companion State ---

    def get_companion_state_device(self, device_token: str) -> dict[str, Any]:
        """Retrieve real-time companion state using device token."""
        resp = self.client.get(
            "/companion/devices/me/state",
            headers={"Authorization": f"Bearer {device_token}"},
        )
        self._record("GET", "/companion/devices/me/state", resp.status_code)
        resp.raise_for_status()
        return resp.json()

    def get_companion_state_user(self, user_token: str, plant_id: str | uuid.UUID) -> dict[str, Any]:
        """Retrieve companion state using user JWT."""
        resp = self.client.get(
            f"/companion/devices/me/state?plant_id={plant_id}",
            headers={"Authorization": f"Bearer {user_token}"},
        )
        self._record("GET", "/companion/devices/me/state", resp.status_code)
        resp.raise_for_status()
        return resp.json()
