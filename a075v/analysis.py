"""Image statistics and 2D diagnostic rendering."""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from .protocol import DEPTH_HEIGHT, DEPTH_WIDTH, Frame


@dataclass(frozen=True)
class DepthMetrics:
    valid_pixels: int
    valid_percent: float
    minimum: int | None
    median: float | None
    maximum: int | None
    center: int | None


def metrics_for(depth: np.ndarray | None) -> DepthMetrics:
    if depth is None:
        return DepthMetrics(0, 0.0, None, None, None, None)
    valid = depth[depth > 0]
    center_value = int(depth[DEPTH_HEIGHT // 2, DEPTH_WIDTH // 2])
    return DepthMetrics(int(valid.size), 100 * valid.size / depth.size, int(valid.min()) if valid.size else None,
                        float(np.median(valid)) if valid.size else None, int(valid.max()) if valid.size else None,
                        center_value or None)


def gaussian_filter_depth(depth: np.ndarray | None, kernel_size: int = 5) -> np.ndarray | None:
    """Gaussian smoothing which preserves invalid (zero) depth pixels."""
    if depth is None:
        return None
    valid = (depth > 0).astype(np.float32)
    weighted = cv2.GaussianBlur(depth.astype(np.float32) * valid, (kernel_size, kernel_size), 0)
    weights = cv2.GaussianBlur(valid, (kernel_size, kernel_size), 0)
    filtered = np.divide(weighted, weights, out=np.zeros_like(weighted), where=weights > 1e-6)
    filtered[valid == 0] = 0
    return np.rint(filtered).astype(depth.dtype)


def channel_summary(image: np.ndarray | None) -> dict[str, object] | None:
    if image is None:
        return None
    nonzero = image[image > 0]
    return {"shape": list(image.shape), "dtype": str(image.dtype), "minimum": int(image.min()),
            "maximum": int(image.max()), "nonzero_pixels": int(nonzero.size),
            "nonzero_median": float(np.median(nonzero)) if nonzero.size else None}


def colourise(image: np.ndarray | None, colormap: int, minimum: int | None = None, maximum: int | None = None) -> np.ndarray:
    if image is None:
        return np.zeros((DEPTH_HEIGHT, DEPTH_WIDTH, 3), dtype=np.uint8)
    lower = int(image.min()) if minimum is None else minimum
    upper = int(image.max()) if maximum is None else maximum
    scaled = np.zeros_like(image, dtype=np.uint8) if upper <= lower else np.clip(
        (image.astype(np.float32) - lower) * 255 / (upper - lower), 0, 255).astype(np.uint8)
    return cv2.applyColorMap(scaled, colormap)


def status_colourise(status: np.ndarray | None) -> np.ndarray:
    """Visualise raw status bytes without claiming undocumented semantics."""
    return colourise(status, cv2.COLORMAP_VIRIDIS, 0, 255)


def _label(image: np.ndarray, text: str, position: tuple[int, int], scale: float = 0.40) -> None:
    thickness = 1 if scale < 0.5 else 2
    cv2.putText(image, text, position, cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), thickness + 1, cv2.LINE_AA)
    cv2.putText(image, text, position, cv2.FONT_HERSHEY_SIMPLEX, scale, (255, 255, 255), thickness, cv2.LINE_AA)


def _depth_scale(height: int, depth_min: int, depth_max: int) -> np.ndarray:
    values = np.linspace(depth_max, depth_min, height, dtype=np.float32).astype(np.uint16).reshape(height, 1)
    bar = cv2.resize(colourise(values, cv2.COLORMAP_TURBO, depth_min, depth_max), (34, height), interpolation=cv2.INTER_NEAREST)
    legend = np.full((height, 100, 3), 25, dtype=np.uint8)
    legend[:, :34] = bar
    _label(legend, str(depth_max), (40, 16), 0.34)
    _label(legend, str((depth_min + depth_max) // 2), (40, height // 2), 0.34)
    _label(legend, str(depth_min), (40, height - 6), 0.34)
    return legend


def _channels(frame: Frame, depth_min: int, depth_max: int) -> dict[str, np.ndarray]:
    depth_view = colourise(frame.depth, cv2.COLORMAP_TURBO, depth_min, depth_max)
    channels = {
        "depth": depth_view,
        "ir": colourise(frame.ir, cv2.COLORMAP_BONE),
        "rgb": cv2.resize(frame.rgb_bgr, (DEPTH_WIDTH, DEPTH_HEIGHT)) if frame.rgb_bgr is not None else np.zeros_like(depth_view),
        "status": status_colourise(frame.status),
    }
    return channels


def compose_diagnostic(frame: Frame, fps: float, depth_min: int, depth_max: int, selected: str | None = None,
                       pointcloud_preview: np.ndarray | None = None) -> np.ndarray:
    channels = _channels(frame, depth_min, depth_max)
    if selected is not None:
        view = cv2.resize(channels[selected], (640, 480), interpolation=cv2.INTER_NEAREST if selected != "rgb" else cv2.INTER_LINEAR)
        _label(view, selected.upper(), (12, 28), 0.55)
        if selected == "depth":
            view = np.hstack((view, _depth_scale(480, depth_min, depth_max)))
        elif selected == "status":
            _label(view, "Raw status bytes: false colour 0–255; see docs/status-channel.md", (12, 462), 0.34)
        return view
    depth_view, ir_view, rgb_view, status_view = (channels[key] for key in ("depth", "ir", "rgb", "status"))
    cloud_view = pointcloud_preview if pointcloud_preview is not None else np.full_like(depth_view, 18)
    if cloud_view.shape[:2] != (DEPTH_HEIGHT, DEPTH_WIDTH):
        cloud_view = cv2.resize(cloud_view, (DEPTH_WIDTH, DEPTH_HEIGHT))
    blank = np.full_like(depth_view, 18)
    for panel, name in ((depth_view, "DEPTH"), (ir_view, "IR"), (rgb_view, "RGB"), (status_view, "STATUS RAW"), (cloud_view, "POINT CLOUD [5]")):
        _label(panel, name, (8, 18), 0.36)
    metrics = metrics_for(frame.depth)
    if metrics.center is not None:
        cv2.drawMarker(depth_view, (DEPTH_WIDTH // 2, DEPTH_HEIGHT // 2), (255, 255, 255), cv2.MARKER_CROSS, 14, 1)
    canvas = np.vstack((np.hstack((depth_view, ir_view, rgb_view)), np.hstack((status_view, cloud_view, blank))))
    median = "-" if metrics.median is None else f"{metrics.median:.0f}"
    _label(canvas, f"frame {frame.frame_id} | {fps:.1f} FPS | valid {metrics.valid_percent:.1f}% | min / median / max: {metrics.minimum} / {median} / {metrics.maximum}", (8, 474), 0.32)
    _label(canvas, f"center {metrics.center} | display range {depth_min}–{depth_max}", (8, 455), 0.32)
    _label(depth_view, f"{depth_min}–{depth_max}", (8, DEPTH_HEIGHT - 9), 0.30)
    return canvas
