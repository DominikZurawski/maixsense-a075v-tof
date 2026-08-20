"""Calibrated ToF geometry and portable PLY export."""

from __future__ import annotations

import time
import math
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from .calibration import RgbCalibration, map_tof_points_to_rgb
from .protocol import DEPTH_HEIGHT, DEPTH_WIDTH, Frame

# Values copied from vendor/sipeed_a075v/calVolumes.py (original Sipeed code).
TOF_FX = 226.5142
TOF_FY = 227.8584
TOF_CX = 163.7246
TOF_CY = 123.3738
DEPTH_UNITS_PER_MM = 4.0


@dataclass(frozen=True)
class PointCloud:
    xyz_mm: np.ndarray
    rgb: np.ndarray
    frame_id: int
    camera_timestamp_ms: int


@dataclass
class OrbitState:
    """Camera state for the in-window Arcball-like point-cloud navigation."""

    yaw: float = -0.45
    pitch: float = 0.25
    distance: float = 1200.0
    pan_x: float = 0.0
    pan_y: float = 0.0

    def reset(self) -> None:
        self.yaw, self.pitch, self.distance, self.pan_x, self.pan_y = -0.45, 0.25, 1200.0, 0.0, 0.0


def orbit_render(cloud: PointCloud | None, width: int, height: int, orbit: OrbitState) -> np.ndarray:
    """Software-render the point cloud for use in the regular OpenCV window."""
    image = np.full((height, width, 3), 18, dtype=np.uint8)
    if cloud is None or not len(cloud.xyz_mm):
        return image
    cy, sy = math.cos(orbit.yaw), math.sin(orbit.yaw)
    cp, sp = math.cos(orbit.pitch), math.sin(orbit.pitch)
    rotation = np.array(((cy, sy * sp, sy * cp), (0, cp, -sp), (-sy, cy * sp, cy * cp)), dtype=np.float32)
    points = cloud.xyz_mm @ rotation.T
    z_camera = points[:, 2] + orbit.distance
    visible = z_camera > 10
    points, z_camera, colours = points[visible], z_camera[visible], cloud.rgb[visible]
    focal = min(width, height) * 1.25
    # The camera's image coordinates use right/down.  Rotate the rendered view
    # by 180 degrees so it matches the orientation requested for the 3D panel.
    px = (width * 0.5 + orbit.pan_x - points[:, 0] * focal / z_camera).astype(np.int32)
    py = (height * 0.5 + orbit.pan_y + points[:, 1] * focal / z_camera).astype(np.int32)
    inside = (px >= 0) & (px < width) & (py >= 0) & (py < height)
    px, py, z_camera, colours = px[inside], py[inside], z_camera[inside], colours[inside]
    order = np.argsort(z_camera)[::-1]  # Distant first; closer points overwrite them.
    image[py[order], px[order]] = colours[order]
    _draw_arcball(image, orbit)
    return image


def _draw_arcball(image: np.ndarray, orbit: OrbitState) -> None:
    """Small corner Arcball control, inspired by the camera's ArcballControls."""
    import cv2

    center = (image.shape[1] - 68, 68)
    radius = 44
    cv2.circle(image, center, radius, (150, 150, 150), 1, cv2.LINE_AA)
    cv2.ellipse(image, center, (radius, 14), 0, 0, 360, (85, 85, 85), 1, cv2.LINE_AA)
    cv2.ellipse(image, center, (14, radius), 0, 0, 360, (85, 85, 85), 1, cv2.LINE_AA)
    x = int(center[0] + radius * 0.75 * math.cos(orbit.yaw))
    y = int(center[1] + radius * 0.75 * math.sin(orbit.pitch))
    cv2.circle(image, (x, y), 4, (255, 255, 255), -1, cv2.LINE_AA)
    cv2.putText(image, "ARC", (center[0] - 14, center[1] + radius + 16), cv2.FONT_HERSHEY_SIMPLEX, 0.32, (190, 190, 190), 1, cv2.LINE_AA)


def frame_to_point_cloud(frame: Frame, stride: int = 2, calibration: RgbCalibration | None = None) -> PointCloud:
    if frame.depth is None or frame.depth.dtype != np.uint16:
        raise ValueError("Point-cloud mode requires 16-bit depth.")
    rows, cols = np.mgrid[0:DEPTH_HEIGHT:stride, 0:DEPTH_WIDTH:stride]
    depth_mm = frame.depth[::stride, ::stride].astype(np.float32) / DEPTH_UNITS_PER_MM
    valid = (depth_mm > 0) & np.isfinite(depth_mm)
    z = depth_mm[valid]
    x = (cols[valid] - TOF_CX) * z / TOF_FX
    y = (rows[valid] - TOF_CY) * z / TOF_FY
    xyz = np.column_stack((x, y, z)).astype(np.float32)
    if not len(xyz):
        return PointCloud(xyz, np.empty((0, 3), dtype=np.uint8), frame.frame_id, frame.timestamp_ms)
    low, high = np.percentile(z, (2, 98))
    scaled = np.clip((z - low) * 255 / max(high - low, 1), 0, 255).astype(np.uint8)
    rgb = cv2.applyColorMap(scaled.reshape(-1, 1), cv2.COLORMAP_TURBO).reshape(-1, 3)[:, ::-1]
    if calibration is not None and frame.rgb_bgr is not None:
        bgr, mapped = map_tof_points_to_rgb(xyz, frame.rgb_bgr, calibration)
        rgb[mapped] = bgr[mapped, ::-1]
    return PointCloud(xyz, rgb, frame.frame_id, frame.timestamp_ms)


def save_ply(cloud: PointCloud, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"a075v_pointcloud_frame{cloud.frame_id}_{int(time.time())}.ply"
    header = ("ply\nformat ascii 1.0\n" f"element vertex {len(cloud.xyz_mm)}\n"
              "property float x\nproperty float y\nproperty float z\n"
              "property uchar red\nproperty uchar green\nproperty uchar blue\nend_header\n")
    with path.open("w", encoding="ascii") as output:
        output.write(header)
        for point, colour in zip(cloud.xyz_mm, cloud.rgb, strict=True):
            output.write(f"{point[0]:.3f} {point[1]:.3f} {point[2]:.3f} {colour[0]} {colour[1]} {colour[2]}\n")
    return path
