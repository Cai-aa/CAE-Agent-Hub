from __future__ import annotations

import json
import os
import socket
import uuid
from pathlib import Path
from typing import Any


MAX_RESPONSE_BYTES = 4 * 1024 * 1024


class BridgeError(RuntimeError):
    pass


def default_config_path() -> Path:
    override = os.environ.get("HYPERWORKS_MCP_BRIDGE_CONFIG", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    local = os.environ.get("LOCALAPPDATA", "").strip()
    base = Path(local) if local else Path.home() / "AppData" / "Local"
    return base / "HyperWorksMCP" / "bridge.json"


class LiveBridgeClient:
    def __init__(self, config_path: Path | None = None):
        self.config_path = (config_path or default_config_path()).expanduser().resolve()

    def _config(self) -> dict[str, Any]:
        if not self.config_path.is_file():
            raise BridgeError(
                f"Live bridge config not found: {self.config_path}. Install and load the HyperWorks Extension."
            )
        value = json.loads(self.config_path.read_text(encoding="utf-8-sig"))
        if value.get("host") != "127.0.0.1":
            raise BridgeError("Live bridge host must be 127.0.0.1")
        if len(str(value.get("token", ""))) < 32:
            raise BridgeError("Live bridge token is missing or invalid")
        return value

    def call(
        self, method: str, params: dict[str, Any] | None = None, timeout: float = 30.0
    ) -> Any:
        config = self._config()
        request = {
            "id": uuid.uuid4().hex,
            "token": config["token"],
            "method": method,
            "params": params or {},
        }
        payload = (json.dumps(request, ensure_ascii=False) + "\n").encode("utf-8")
        try:
            with socket.create_connection(
                (config["host"], int(config["port"])), timeout=timeout
            ) as connection:
                connection.settimeout(timeout)
                connection.sendall(payload)
                data = bytearray()
                while b"\n" not in data:
                    chunk = connection.recv(65536)
                    if not chunk:
                        break
                    data.extend(chunk)
                    if len(data) > MAX_RESPONSE_BYTES:
                        raise BridgeError("Live bridge response exceeded 4 MB")
        except (OSError, TimeoutError) as exc:
            raise BridgeError(
                f"Cannot reach the live HyperWorks bridge at {config['host']}:{config['port']}: {exc}"
            ) from exc
        if not data:
            raise BridgeError("Live bridge closed the connection without a response")
        response = json.loads(bytes(data).split(b"\n", 1)[0].decode("utf-8"))
        if response.get("id") != request["id"]:
            raise BridgeError("Live bridge response ID mismatch")
        if not response.get("ok"):
            error = response.get("error", {})
            raise BridgeError(
                f"{error.get('code', 'BRIDGE_ERROR')}: {error.get('message', 'Unknown bridge error')}"
            )
        return response.get("result")

    def status(self, connect_timeout: float = 0.5) -> dict[str, Any]:
        status_path = self.config_path.with_name("status.json")
        persisted = None
        if status_path.is_file():
            try:
                persisted = json.loads(status_path.read_text(encoding="utf-8-sig"))
            except Exception as exc:
                persisted = {"state": "invalid", "error": str(exc)}
        try:
            ping = self.call("ping", timeout=connect_timeout)
            connected = True
            error = None
        except Exception as exc:
            ping = None
            connected = False
            error = str(exc)
        return {
            "connected": connected,
            "config_path": str(self.config_path),
            "status_path": str(status_path),
            "persisted_status": persisted,
            "ping": ping,
            "error": error,
        }
