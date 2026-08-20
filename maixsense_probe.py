#!/usr/bin/env python3
"""Stable command entry point; application code lives in the ``a075v`` package."""

from __future__ import annotations

import os

# The pip OpenCV wheel uses XWayland under GNOME Wayland.
if os.environ.get("XDG_SESSION_TYPE") == "wayland":
    os.environ["XDG_SESSION_TYPE"] = "x11"

from a075v.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
