"""Capture artefacts, calibration metadata and per-frame telemetry."""

from __future__ import annotations

import json
import hashlib
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np

from .analysis import channel_summary, colourise, metrics_for
from .protocol import Frame


def calibration_summary(path: Path) -> dict[str, object]:
    """Return calibration metadata without exposing a local absolute path."""
    try:
        display_path = str(path.resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        display_path = path.name
    if not path.exists():
        return {"available": False, "path": display_path}
    data = json.loads(path.read_text(encoding="utf-8"))
    matrix = data.get("Camera_Matrix_data", [])
    return {"available": True, "path": display_path, "rgb_intrinsics":
            {"fx": matrix[0], "fy": matrix[4], "cx": matrix[2], "cy": matrix[5]} if len(matrix) == 9 else None}


class TelemetryLog:
    def __init__(self, path: Path | None, raw_directory: Path | None) -> None:
        self.file = None
        self.raw_directory = raw_directory
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            self.file = path.open("a", encoding="utf-8")
        if raw_directory is not None:
            raw_directory.mkdir(parents=True, exist_ok=True)

    def write(self, frame: Frame, fps: float) -> None:
        record = {"received_at_utc": datetime.now(timezone.utc).isoformat(), "frame_id": frame.frame_id,
                  "camera_timestamp_ms": frame.timestamp_ms, "fps_rolling": round(fps, 3), "packet_bytes": len(frame.raw),
                  "stream_config": asdict(frame.config), "depth": channel_summary(frame.depth), "ir": channel_summary(frame.ir),
                  "status": channel_summary(frame.status), "rgb": {"payload_bytes": len(frame.rgb_payload),
                  "decoded": frame.rgb_bgr is not None, "shape": None if frame.rgb_bgr is None else list(frame.rgb_bgr.shape),
                  "dtype": None if frame.rgb_bgr is None else str(frame.rgb_bgr.dtype)}}
        if self.file is not None:
            self.file.write(json.dumps(record, ensure_ascii=False) + "\n")
            self.file.flush()
        if self.raw_directory is not None:
            (self.raw_directory / f"frame_{frame.frame_id:08d}_{frame.timestamp_ms}.raw").write_bytes(frame.raw)

    def close(self) -> None:
        if self.file is not None:
            self.file.close()


def save_capture(frame: Frame, directory: Path, calibration: dict[str, object], depth_min: int, depth_max: int) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    stem = directory / f"a075v_{datetime.now().strftime('%Y%m%dT%H%M%S')}_frame{frame.frame_id}"
    stem.with_suffix(".raw").write_bytes(frame.raw)
    if frame.depth is not None:
        np.save(str(stem) + "_depth.npy", frame.depth)
        cv2.imwrite(str(stem) + "_depth_preview.png", colourise(frame.depth, cv2.COLORMAP_TURBO, depth_min, depth_max))
    if frame.ir is not None:
        np.save(str(stem) + "_ir.npy", frame.ir)
        cv2.imwrite(str(stem) + "_ir_preview.png", colourise(frame.ir, cv2.COLORMAP_BONE))
    if frame.status is not None:
        np.save(str(stem) + "_status.npy", frame.status)
    if frame.rgb_bgr is not None:
        cv2.imwrite(str(stem) + "_rgb.png", frame.rgb_bgr)
    if frame.config.rgb_mode == 0 and frame.rgb_payload:
        Path(str(stem) + "_rgb.yuv").write_bytes(frame.rgb_payload)
    metadata = {"captured_at_utc": datetime.now(timezone.utc).isoformat(), "frame_id": frame.frame_id,
                "camera_timestamp_ms": frame.timestamp_ms, "stream_config": asdict(frame.config),
                "depth_metrics": asdict(metrics_for(frame.depth)), "depth_visual_range": {"min": depth_min, "max": depth_max},
                "rgb": {"payload_bytes": len(frame.rgb_payload), "decoded": frame.rgb_bgr is not None,
                        "shape": None if frame.rgb_bgr is None else list(frame.rgb_bgr.shape)},
                "calibration": calibration}
    Path(str(stem) + "_metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    return stem


def save_camera_resources(directory: Path, capture_stem: Path, resources: dict[str, bytes], errors: dict[str, str]) -> Path:
    """Save auxiliary camera resources beside one capture and describe the bundle."""
    directory.mkdir(parents=True, exist_ok=True)
    files: dict[str, dict[str, object]] = {}
    for filename, content in resources.items():
        path = directory / filename
        path.write_bytes(content)
        files[filename] = {"bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()}
    manifest = {
        "purpose": "Supplementary camera resources captured with an A075V test frame.",
        "capture_stem": capture_stem.name,
        "resources": files,
        "unavailable_resources": errors,
    }
    (directory / "camera_resources_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (directory / "README.md").write_text(
        "# Zestaw testowy MaixSense-A075V\n\n"
        "Ten katalog zawiera jedną ramkę pomiarową oraz wszystkie dodatkowe zasoby "
        "udostępnione przez HTTP kamery w chwili przechwycenia.\n\n"
        "- `*_depth.npy` — 16-bitowa mapa głębi ToF, `uint16`, 320×240; `Z_mm = raw / 4`.\n"
        "- `*_ir.npy` — kanał IR; `*_rgb.png` — odebrany obraz RGB.\n"
        "- `*_rgb.yuv` — oryginalny bufor RGB, obecny tylko dla trybu YUV.\n"
        "- `*.raw` — kompletny pakiet protokołu; `*_metadata.json` — konfiguracja ramki.\n"
        "- `CameraParms.json` — kalibracja RGB–ToF pobrana z kamery.\n"
        "- `getinfo.bin`, `get_lut.bin` — binarne zasoby firmware; ich format nie jest "
        "opisany tekstowo przez producenta.\n"
        "- `plane_test.json` — wynik dopasowania płaszczyzny dla tej samej ramki, jeżeli "
        "przechwycenie było testem ściany.\n"
        "- `camera_resources_manifest.json` — rozmiary, sumy SHA-256 i ewentualne błędy pobrania.\n",
        encoding="utf-8",
    )
    return directory
