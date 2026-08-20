"""A075V HTTP stream configuration and binary frame decoder."""

from __future__ import annotations

import struct
from dataclasses import dataclass

import cv2
import numpy as np

DEPTH_WIDTH = 320
DEPTH_HEIGHT = 240


@dataclass(frozen=True)
class StreamSettings:
    depth_bits: int = 8
    ir_bits: int = 8
    rgb: bool = True
    rgb_resolution: int = 800
    rgb_format: str = "jpeg"

    def encode(self) -> bytes:
        if self.rgb_resolution not in (800, 1600):
            raise ValueError("RGB resolution must be 800 or 1600 pixels wide.")
        if self.rgb_format not in ("jpeg", "yuv"):
            raise ValueError("RGB format must be 'jpeg' or 'yuv'.")
        depth_mode = 0 if self.depth_bits == 16 else 1
        ir_mode = 0 if self.ir_bits == 16 else 1
        rgb_mode = {"yuv": 0, "jpeg": 1}[self.rgb_format] if self.rgb else 2
        rgb_resolution_mode = 0 if self.rgb_resolution == 800 else 1
        return struct.pack("<BBBBBBBBi", 1, depth_mode, 255, ir_mode, 2, 7, rgb_mode, rgb_resolution_mode, 0)


@dataclass(frozen=True)
class FrameConfig:
    trigger_mode: int
    depth_mode: int
    depth_shift: int
    ir_mode: int
    status_mode: int
    status_mask: int
    rgb_mode: int
    rgb_resolution: int
    exposure_time: int


@dataclass
class Frame:
    frame_id: int
    timestamp_ms: int
    config: FrameConfig
    depth: np.ndarray | None
    ir: np.ndarray | None
    status: np.ndarray | None
    rgb_bgr: np.ndarray | None
    rgb_payload: bytes
    raw: bytes


def decode_frame(raw: bytes) -> Frame:
    """Decode the binary response from the camera's ``/getdeep`` endpoint."""
    if len(raw) < 36:
        raise ValueError(f"Frame is too short ({len(raw)} bytes; need at least 36).")
    frame_id, timestamp_ms = struct.unpack_from("<QQ", raw, 0)
    config = FrameConfig(*struct.unpack_from("<BBBBBBBBi", raw, 16))
    depth_and_aux_size, rgb_size = struct.unpack_from("<ii", raw, 28)
    if depth_and_aux_size < 0 or rgb_size < 0:
        raise ValueError("Negative section size in frame header.")
    if len(raw) != 36 + depth_and_aux_size + rgb_size:
        raise ValueError("Frame length does not match its header.")
    depth_bytes = (DEPTH_WIDTH * DEPTH_HEIGHT * 2) >> config.depth_mode
    ir_bytes = (DEPTH_WIDTH * DEPTH_HEIGHT * 2) >> config.ir_mode
    status_bytes = (DEPTH_WIDTH * DEPTH_HEIGHT // 8) * {0: 16, 1: 2, 2: 8}.get(config.status_mode, 1)
    if depth_bytes + ir_bytes + status_bytes != depth_and_aux_size:
        raise ValueError("Frame configuration and payload sizes disagree.")
    offset = 36

    def mono(section: bytes, mode: int) -> np.ndarray:
        return np.frombuffer(section, dtype=np.uint16 if mode == 0 else np.uint8).reshape(DEPTH_HEIGHT, DEPTH_WIDTH)

    depth = mono(raw[offset : offset + depth_bytes], config.depth_mode)
    offset += depth_bytes
    ir = mono(raw[offset : offset + ir_bytes], config.ir_mode)
    offset += ir_bytes
    status = mono(raw[offset : offset + status_bytes], 0 if config.status_mode == 0 else 1)
    offset += status_bytes
    rgb_payload = raw[offset : offset + rgb_size]
    rgb_bgr = None
    if config.rgb_mode == 1 and rgb_payload:
        rgb_bgr = cv2.imdecode(np.frombuffer(rgb_payload, np.uint8), cv2.IMREAD_COLOR)
    elif config.rgb_mode == 0 and rgb_payload:
        # The vendor tutorial identifies this as planar YUV420. Decode it only
        # when its byte count exactly matches the selected resolution.
        width, height = (800, 600) if config.rgb_resolution == 0 else (1600, 1200)
        if len(rgb_payload) == width * height * 3 // 2:
            yuv = np.frombuffer(rgb_payload, np.uint8).reshape(height * 3 // 2, width)
            rgb_bgr = cv2.cvtColor(yuv, cv2.COLOR_YUV2BGR_I420)
    return Frame(frame_id, timestamp_ms, config, depth, ir, status, rgb_bgr, rgb_payload, raw)
