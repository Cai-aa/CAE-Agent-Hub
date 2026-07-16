from __future__ import annotations

from .bridge import BridgeRuntime


_runtime: BridgeRuntime | None = None


def load() -> BridgeRuntime:
    global _runtime
    if _runtime is None:
        _runtime = BridgeRuntime()
        _runtime.start()
    return _runtime


def unload() -> None:
    global _runtime
    if _runtime is not None:
        _runtime.stop()
        _runtime = None


def get_runtime() -> BridgeRuntime | None:
    return _runtime
