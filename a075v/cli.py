"""Command-line orchestration for the A075V workbench."""

from __future__ import annotations

import argparse
import json
import logging
import time
import webbrowser
from collections import deque
from dataclasses import asdict, replace
from datetime import datetime
from pathlib import Path

import cv2
import numpy as np
import requests

from .analysis import compose_diagnostic, gaussian_filter_depth
from .calibration import load_rgb_calibration
from .geometry import fit_plane
from .persistence import TelemetryLog, calibration_summary, save_camera_resources, save_capture
from .pointcloud import OrbitState, frame_to_point_cloud, orbit_render, save_ply
from .protocol import StreamSettings
from .transport import CameraClient

PROJECT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_CALIBRATION = PROJECT_DIR / "vendor" / "sipeed_a075v" / "CameraParms.json"
LOG = logging.getLogger("maixsense")


def _error_canvas(message: str) -> np.ndarray:
    image = np.zeros((480, 640, 3), dtype=np.uint8)
    cv2.putText(image, "Waiting for MaixSense-A075V…", (20, 220), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)
    cv2.putText(image, message[:82], (20, 250), cv2.FONT_HERSHEY_SIMPLEX, 0.35, (255, 255, 255), 1)
    return image


def _mouse_wheel_delta(flags: int) -> int:
    """Decode OpenCV's wheel delta without relying on unavailable helper APIs."""
    delta = (flags >> 16) & 0xFFFF
    return delta - 0x10000 if delta & 0x8000 else delta


def _plane_report(result: object) -> str:
    """Use the same concise plane-test wording in the UI and one-shot capture."""
    return (f"plane: Zc {result.z_center_mm:.1f} | R {result.range_center_mm:.1f} mm | "
            f"edge-centre {result.edge_minus_center_percent:+.1f}% | tilt {result.normal_angle_deg:.1f} deg | "
            f"RMS {result.rms_error_mm:.1f} mm")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Professional RGB-D diagnostic and capture tool for Sipeed MaixSense-A075V.")
    parser.add_argument("--host", default="192.168.233.1")
    parser.add_argument("--source-address", default="auto", help="RNDIS address, or auto (default)")
    parser.add_argument("--timeout", type=float, default=3.0)
    parser.add_argument("--depth-bits", choices=(8, 16), type=int, default=16)
    parser.add_argument("--ir-bits", choices=(8, 16), type=int, default=8)
    parser.add_argument("--no-rgb", action="store_true")
    parser.add_argument("--rgb-resolution", choices=(800, 1600), type=int, default=800,
                        help="Requested RGB width; firmware modes are 800x600 and 1600x1200")
    parser.add_argument("--rgb-format", choices=("jpeg", "yuv"), default="jpeg",
                        help="JPEG (default) or experimental planar YUV420 from the camera protocol")
    parser.add_argument("--depth-min", type=int, default=0)
    parser.add_argument("--depth-max", type=int, default=8000)
    parser.add_argument("--save-dir", type=Path, default=Path("captures"))
    parser.add_argument("--calibration", type=Path, default=DEFAULT_CALIBRATION)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--test-bundle-dir", type=Path,
                        help="With --once: save frame plus CameraParms.json, getinfo and get_lut in this folder")
    parser.add_argument("--telemetry-log", type=Path)
    parser.add_argument("--no-telemetry-log", action="store_true")
    parser.add_argument("--record-raw-dir", type=Path)
    parser.add_argument("--open-camera-viewer", action="store_true")
    parser.add_argument("--point-cloud", action="store_true")
    parser.add_argument("--cloud-stride", type=int, default=2)
    parser.add_argument("--cloud-save-dir", type=Path, default=Path("pointclouds"))
    parser.add_argument("--verbose", action="store_true")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.depth_max <= args.depth_min:
        parser.error("--depth-max must be greater than --depth-min")
    if args.cloud_stride < 1:
        parser.error("--cloud-stride must be at least 1")
    if args.test_bundle_dir is not None and not args.once:
        parser.error("--test-bundle-dir requires --once")
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s: %(message)s")
    if args.open_camera_viewer:
        opened = webbrowser.open(f"http://{args.host}/")
        print("Opened camera point-cloud viewer in the default browser." if opened else f"Open http://{args.host}/ in a browser.")
        return 0

    calibration = calibration_summary(args.calibration)
    rgb_calibration = load_rgb_calibration(args.calibration) if args.calibration.exists() else None
    telemetry_path = None if args.no_telemetry_log else args.telemetry_log or Path("logs") / f"a075v_{datetime.now().strftime('%Y%m%dT%H%M%S')}.jsonl"
    telemetry = TelemetryLog(telemetry_path, args.record_raw_dir)
    base_settings = StreamSettings(args.depth_bits, args.ir_bits, not args.no_rgb, args.rgb_resolution, args.rgb_format)
    settings = StreamSettings(depth_bits=16, ir_bits=args.ir_bits, rgb=False, rgb_resolution=args.rgb_resolution, rgb_format=args.rgb_format) if args.point_cloud else base_settings
    client = CameraClient(args.host, args.source_address, args.timeout)
    try:
        client.configure(settings)
        LOG.info("Connected to %s via %s; depth=%d-bit, IR=%d-bit, RGB=%s (%s)", args.host, client.source_address or "system route", settings.depth_bits, settings.ir_bits, settings.rgb, args.rgb_format)
        if args.once:
            frame = client.get_frame()
            telemetry.write(frame, 0.0)
            capture_depth_min, capture_depth_max = args.depth_min, args.depth_max
            if frame.depth is not None and np.any(frame.depth > 0):
                valid_depth = frame.depth[frame.depth > 0]
                capture_depth_min = int(np.percentile(valid_depth, 2))
                capture_depth_max = max(int(np.percentile(valid_depth, 98)), capture_depth_min + 1)
                LOG.info("Depth preview range (automatic): %d..%d raw (%0.1f..%0.1f mm)",
                         capture_depth_min, capture_depth_max, capture_depth_min / 4, capture_depth_max / 4)
            capture_directory = args.test_bundle_dir or args.save_dir
            capture_stem = save_capture(frame, capture_directory, calibration, capture_depth_min, capture_depth_max)
            if frame.rgb_bgr is not None:
                LOG.info("Received RGB image: %dx%d (requested %dx%d, %s)", frame.rgb_bgr.shape[1], frame.rgb_bgr.shape[0], args.rgb_resolution, args.rgb_resolution * 3 // 4, args.rgb_format)
            elif not args.no_rgb:
                LOG.warning("RGB payload was not decoded: %d bytes (requested %dx%d, %s)", len(frame.rgb_payload), args.rgb_resolution, args.rgb_resolution * 3 // 4, args.rgb_format)
            if args.test_bundle_dir is not None:
                resources: dict[str, bytes] = {}
                errors: dict[str, str] = {}
                for filename, endpoint in (("CameraParms.json", "CameraParms.json"), ("getinfo.bin", "getinfo"), ("get_lut.bin", "get_lut")):
                    try:
                        resources[filename] = client.get_resource(endpoint)
                    except requests.RequestException as exc:
                        errors[filename] = str(exc)
                bundle = save_camera_resources(args.test_bundle_dir, capture_stem, resources, errors)
                try:
                    if frame.depth is None:
                        raise ValueError("Depth channel is unavailable in this frame.")
                    plane_metrics = fit_plane(frame.depth)
                    LOG.info("Plane test: %s", _plane_report(plane_metrics))
                    (bundle / "plane_test.json").write_text(
                        json.dumps({"capture_stem": capture_stem.name, "metrics": asdict(plane_metrics)}, indent=2) + "\n",
                        encoding="utf-8",
                    )
                except ValueError as exc:
                    (bundle / "plane_test.json").write_text(
                        json.dumps({"capture_stem": capture_stem.name, "unavailable": str(exc)}, indent=2) + "\n",
                        encoding="utf-8",
                    )
                print(f"Saved test bundle: {bundle}")
            else:
                print(f"Saved capture: {capture_stem}")
            return 0
        window = "MaixSense-A075V | s: save, a: auto range, q/Esc: quit"
        cv2.namedWindow(window, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(window, 1200, 720)
        times: deque[float] = deque(maxlen=30)
        auto_range = False
        gaussian_enabled = False
        rgb_map_enabled = False
        selected_channel: str | None = "pointcloud" if args.point_cloud else None
        orbit = OrbitState()
        cloud = None
        last_processed_frame = None
        plane_report = ""
        drag_origin: tuple[int, int] | None = None

        def select_channel(event: int, x: int, y: int, flags: int, param: object) -> None:
            nonlocal selected_channel, drag_origin
            if selected_channel == "pointcloud":
                if event == cv2.EVENT_LBUTTONDOWN:
                    drag_origin = (x, y)
                elif event == cv2.EVENT_MOUSEMOVE and drag_origin is not None and flags & cv2.EVENT_FLAG_LBUTTON:
                    orbit.yaw += (x - drag_origin[0]) * 0.008
                    orbit.pitch = float(np.clip(orbit.pitch + (y - drag_origin[1]) * 0.008, -1.5, 1.5))
                    drag_origin = (x, y)
                elif event == cv2.EVENT_RBUTTONDOWN:
                    drag_origin = (x, y)
                elif event == cv2.EVENT_MOUSEMOVE and drag_origin is not None and flags & cv2.EVENT_FLAG_RBUTTON:
                    orbit.pan_x += x - drag_origin[0]
                    orbit.pan_y += y - drag_origin[1]
                    drag_origin = (x, y)
                elif event in (cv2.EVENT_LBUTTONUP, cv2.EVENT_RBUTTONUP):
                    drag_origin = None
                elif event == cv2.EVENT_MOUSEWHEEL:
                    orbit.distance *= 0.85 if _mouse_wheel_delta(flags) > 0 else 1.18
                    orbit.distance = float(np.clip(orbit.distance, 100.0, 20000.0))
                return
            if event != cv2.EVENT_LBUTTONUP:
                return
            if selected_channel is not None:
                selected_channel = None
                return
            column, row = x // 320, y // 240
            selected_channel = (("depth", "ir", "rgb"), ("status", "pointcloud", None))[row][column]

        cv2.setMouseCallback(window, select_channel)
        while True:
            try:
                target_settings = StreamSettings(depth_bits=16, ir_bits=args.ir_bits, rgb=rgb_map_enabled, rgb_resolution=args.rgb_resolution, rgb_format=args.rgb_format) if selected_channel == "pointcloud" else base_settings
                if settings != target_settings:
                    settings = target_settings
                    client.configure(settings)
                frame = client.get_frame()
                now = time.monotonic()
                times.append(now)
                fps = (len(times) - 1) / (times[-1] - times[0]) if len(times) > 1 else 0.0
                telemetry.write(frame, fps)
                if auto_range and frame.depth is not None and np.any(frame.depth > 0):
                    valid = frame.depth[frame.depth > 0]
                    args.depth_min, args.depth_max = int(np.percentile(valid, 2)), max(int(np.percentile(valid, 98)), int(np.percentile(valid, 2)) + 1)
                processed_frame = replace(frame, depth=gaussian_filter_depth(frame.depth) if gaussian_enabled else frame.depth)
                last_processed_frame = processed_frame
                if selected_channel == "pointcloud":
                    if processed_frame.depth is None or processed_frame.depth.dtype != np.uint16:
                        # The device may deliver one stale frame after POST /set_cfg.
                        client.configure(settings)
                        view = _error_canvas("Switching camera to 16-bit depth for point cloud…")
                    else:
                        cloud = frame_to_point_cloud(processed_frame, args.cloud_stride, rgb_calibration if rgb_map_enabled else None)
                        view = orbit_render(cloud, 800, 600, orbit)
                else:
                    if processed_frame.depth is not None and processed_frame.depth.dtype == np.uint16:
                        cloud = frame_to_point_cloud(processed_frame, args.cloud_stride)
                    preview = orbit_render(cloud, 320, 240, OrbitState()) if cloud is not None else None
                    view = compose_diagnostic(processed_frame, fps, args.depth_min, args.depth_max, selected_channel, preview)
                if plane_report:
                    cv2.putText(view, plane_report, (12, 42), cv2.FONT_HERSHEY_SIMPLEX, 0.38, (255, 255, 255), 1, cv2.LINE_AA)
            except (requests.RequestException, ValueError) as exc:
                LOG.warning("Frame unavailable; retrying: %s", exc)
                view = _error_canvas(str(exc))
                try:
                    client.configure(settings)
                except requests.RequestException:
                    pass
                frame = None
                time.sleep(0.15)
            cv2.imshow(window, view)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break
            if key == ord("a"):
                auto_range = not auto_range
            if key == ord("g"):
                gaussian_enabled = not gaussian_enabled
                LOG.info("Gaussian depth filter: %s", "on" if gaussian_enabled else "off")
            if key == ord("p") and last_processed_frame is not None and last_processed_frame.depth is not None:
                try:
                    result = fit_plane(last_processed_frame.depth)
                    plane_report = _plane_report(result)
                    LOG.info("Plane test: %s", plane_report)
                except ValueError as exc:
                    plane_report = f"Plane test unavailable: {exc}"
            if key in (ord("1"), ord("2"), ord("3"), ord("4")):
                if selected_channel == "pointcloud":
                    settings = base_settings
                    client.configure(settings)
                selected_channel = ("depth", "ir", "rgb", "status")[key - ord("1")]
            if key == ord("0"):
                if selected_channel == "pointcloud":
                    settings = base_settings
                    client.configure(settings)
                selected_channel = None
            if key == ord("5"):
                if settings.depth_bits != 16:
                    settings = StreamSettings(depth_bits=16, ir_bits=args.ir_bits, rgb=rgb_map_enabled, rgb_resolution=args.rgb_resolution, rgb_format=args.rgb_format)
                    client.configure(settings)
                selected_channel = "pointcloud"
            if key == ord("c") and selected_channel == "pointcloud":
                rgb_map_enabled = not rgb_map_enabled
                LOG.info("Calibrated RGB map: %s", "on" if rgb_map_enabled else "off")
            if key == ord("r") and selected_channel == "pointcloud":
                orbit.reset()
            if key == ord("s") and frame is not None:
                if selected_channel == "pointcloud" and cloud is not None:
                    LOG.info("Saved point cloud: %s", save_ply(cloud, args.cloud_save_dir))
                else:
                    LOG.info("Saved capture: %s", save_capture(frame, args.save_dir, calibration, args.depth_min, args.depth_max))
    except (requests.RequestException, ValueError, OSError) as exc:
        LOG.error("Cannot start camera stream: %s", exc)
        print("Camera unavailable. Verify the USB RNDIS link and README.md.")
        return 1
    finally:
        cv2.destroyAllWindows()
        client.close()
        telemetry.close()
    return 0
