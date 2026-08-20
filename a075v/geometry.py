"""Geometry derived from the 16-bit ToF depth map."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .pointcloud import DEPTH_UNITS_PER_MM, TOF_CX, TOF_CY, TOF_FX, TOF_FY


@dataclass(frozen=True)
class PlaneMetrics:
    point_count: int
    z_center_mm: float
    range_center_mm: float
    plane_distance_mm: float
    normal_angle_deg: float
    rms_error_mm: float
    center_median_mm: float
    edge_median_mm: float
    edge_minus_center_percent: float


def depth_to_xyz_mm(depth: np.ndarray) -> np.ndarray:
    """Convert a 16-bit depth image into an XYZ image in ToF-camera mm."""
    if depth.dtype != np.uint16:
        raise ValueError("Geometry requires 16-bit depth.")
    rows, cols = np.indices(depth.shape, dtype=np.float32)
    z = depth.astype(np.float32) / DEPTH_UNITS_PER_MM
    x = (cols - TOF_CX) * z / TOF_FX
    y = (rows - TOF_CY) * z / TOF_FY
    return np.dstack((x, y, z))


def range_map_mm(depth: np.ndarray) -> np.ndarray:
    """Distance R from the camera origin, rather than axial depth Z."""
    xyz = depth_to_xyz_mm(depth)
    return np.linalg.norm(xyz, axis=2)


def normal_map(depth: np.ndarray) -> np.ndarray:
    """Estimate unit surface normals from neighbouring XYZ points; invalid pixels are zero."""
    xyz = depth_to_xyz_mm(depth)
    dy, dx = np.gradient(xyz, axis=(0, 1))
    normals = np.cross(dx, dy)
    lengths = np.linalg.norm(normals, axis=2, keepdims=True)
    normals = np.divide(normals, lengths, out=np.zeros_like(normals), where=lengths > 1e-6)
    normals[normals[:, :, 2] > 0] *= -1  # Face the sensor consistently.
    normals[depth == 0] = 0
    return normals


def fit_plane(depth: np.ndarray, stride: int = 4) -> PlaneMetrics:
    """Least-squares plane fit for a scene dominated by one planar target."""
    xyz = depth_to_xyz_mm(depth)[::stride, ::stride].reshape(-1, 3)
    xyz = xyz[xyz[:, 2] > 0]
    if len(xyz) < 3:
        raise ValueError("Not enough valid depth points to fit a plane.")
    centroid = xyz.mean(axis=0)
    _, _, vh = np.linalg.svd(xyz - centroid, full_matrices=False)
    normal = vh[-1]
    if normal[2] < 0:
        normal = -normal
    residuals = (xyz - centroid) @ normal
    center_xyz = depth_to_xyz_mm(depth)[depth.shape[0] // 2, depth.shape[1] // 2]
    depth_mm = depth.astype(np.float32) / DEPTH_UNITS_PER_MM
    height, width = depth.shape
    centre = depth_mm[height // 2 - 20 : height // 2 + 20, width // 2 - 20 : width // 2 + 20]
    edges = np.concatenate((depth_mm[:, :20].ravel(), depth_mm[:, -20:].ravel()))
    centre = centre[centre > 0]
    edges = edges[edges > 0]
    center_median = float(np.median(centre)) if len(centre) else float("nan")
    edge_median = float(np.median(edges)) if len(edges) else float("nan")
    return PlaneMetrics(
        point_count=len(xyz),
        z_center_mm=float(center_xyz[2]),
        range_center_mm=float(np.linalg.norm(center_xyz)),
        plane_distance_mm=float(abs(centroid @ normal)),
        normal_angle_deg=float(np.degrees(np.arccos(np.clip(normal[2], -1, 1)))),
        rms_error_mm=float(np.sqrt(np.mean(residuals * residuals))),
        center_median_mm=center_median,
        edge_median_mm=edge_median,
        edge_minus_center_percent=float((edge_median - center_median) * 100 / center_median) if center_median else float("nan"),
    )
