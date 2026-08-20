"""Projection between the ToF and RGB cameras using copied Sipeed calibration."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass(frozen=True)
class RgbCalibration:
    rotation: np.ndarray
    translation_mm: np.ndarray
    camera_matrix: np.ndarray
    distortion: np.ndarray


def load_rgb_calibration(path: Path) -> RgbCalibration:
    data = json.loads(path.read_text(encoding="utf-8"))
    return RgbCalibration(
        np.asarray(data["R_Matrix_data"], dtype=np.float32).reshape(3, 3),
        np.asarray(data["T_Vec_data"], dtype=np.float32),
        np.asarray(data["Camera_Matrix_data"], dtype=np.float32).reshape(3, 3),
        np.asarray(data["Distortion_Parm_data"], dtype=np.float32),
    )


def map_tof_points_to_rgb(points_mm: np.ndarray, rgb_bgr: np.ndarray, calibration: RgbCalibration) -> tuple[np.ndarray, np.ndarray]:
    """Return BGR colours and a validity mask for ToF points projected into RGB."""
    camera_points = points_mm @ calibration.rotation.T + calibration.translation_mm
    z = camera_points[:, 2]
    valid = z > 1e-6
    normalized = np.zeros((len(points_mm), 2), dtype=np.float32)
    normalized[valid] = camera_points[valid, :2] / z[valid, None]
    x, y = normalized[:, 0], normalized[:, 1]
    k1, k2, p1, p2, k3 = calibration.distortion
    r2 = x * x + y * y
    radial = 1 + k1 * r2 + k2 * r2 * r2 + k3 * r2 * r2 * r2
    xd = x * radial + 2 * p1 * x * y + p2 * (r2 + 2 * x * x)
    yd = y * radial + p1 * (r2 + 2 * y * y) + 2 * p2 * x * y
    # Original RGB calibration is 800×600; scale it to the received JPEG size.
    sx, sy = rgb_bgr.shape[1] / 800.0, rgb_bgr.shape[0] / 600.0
    u = np.rint((calibration.camera_matrix[0, 0] * xd + calibration.camera_matrix[0, 2]) * sx).astype(np.int32)
    v = np.rint((calibration.camera_matrix[1, 1] * yd + calibration.camera_matrix[1, 2]) * sy).astype(np.int32)
    valid &= (u >= 0) & (u < rgb_bgr.shape[1]) & (v >= 0) & (v < rgb_bgr.shape[0])
    colours = np.zeros((len(points_mm), 3), dtype=np.uint8)
    colours[valid] = rgb_bgr[v[valid], u[valid]]
    return colours, valid
