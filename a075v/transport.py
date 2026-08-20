"""Network transport for A075V's RNDIS HTTP interface."""

from __future__ import annotations

import socket

import requests
from requests.adapters import HTTPAdapter

from .protocol import Frame, StreamSettings, decode_frame


class SourceAddressAdapter(HTTPAdapter):
    def __init__(self, source_address: str, **kwargs: object) -> None:
        self.source_address = source_address
        super().__init__(**kwargs)

    def init_poolmanager(self, connections: int, maxsize: int, block: bool = False, **kwargs: object) -> None:
        kwargs["source_address"] = (self.source_address, 0)
        super().init_poolmanager(connections, maxsize, block=block, **kwargs)


def resolve_source_address(host: str, requested: str) -> str | None:
    if requested.lower() not in {"", "auto"}:
        return requested
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
        probe.connect((host, 80))
        return str(probe.getsockname()[0])


class CameraClient:
    """Configures and retrieves frames from one A075V camera."""

    def __init__(self, host: str, source_address: str = "auto", timeout: float = 3.0) -> None:
        self.host, self.timeout = host, timeout
        self.source_address = resolve_source_address(host, source_address)
        self.session = requests.Session()
        if self.source_address:
            self.session.mount("http://", SourceAddressAdapter(self.source_address))

    def configure(self, settings: StreamSettings) -> None:
        response = self.session.post(
            f"http://{self.host}/set_cfg",
            data=settings.encode(),
            headers={"Content-Type": "application/octet-stream"},
            timeout=self.timeout,
        )
        response.raise_for_status()

    def get_frame(self) -> Frame:
        response = self.session.get(f"http://{self.host}/getdeep", headers={"Cache-Control": "no-cache"}, timeout=self.timeout)
        response.raise_for_status()
        return decode_frame(response.content)

    def get_resource(self, path: str) -> bytes:
        """Retrieve a documented auxiliary resource from the camera HTTP server."""
        response = self.session.get(f"http://{self.host}/{path.lstrip('/')}", headers={"Cache-Control": "no-cache"}, timeout=self.timeout)
        response.raise_for_status()
        return response.content

    def close(self) -> None:
        self.session.close()
