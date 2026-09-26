"""Run this file inside ANSA to start the authenticated MCP bridge."""

from datetime import datetime, timezone
import json
import os
import sys
import traceback


def _bridge_config_path():
    # ANSA and an MCP host can see different LOCALAPPDATA values (notably when
    # the host is a packaged Windows app). The installer writes only the
    # absolute config *path* beside this script, never the bearer token.
    script_path = globals().get("__file__")
    if script_path:
        plugin_root = os.path.dirname(os.path.abspath(script_path))
        pointer = os.path.join(plugin_root, "bridge_config_path.txt")
        if os.path.isfile(pointer):
            with open(pointer, "r", encoding="utf-8-sig") as stream:
                target = stream.read().strip()
            if not os.path.isabs(target) or not os.path.isfile(target):
                raise RuntimeError("ANSA MCP config pointer is not an existing absolute file")
            with open(target, "r", encoding="utf-8-sig") as stream:
                config = json.load(stream)
            configured_root = config.get("plugin_root") if isinstance(config, dict) else None
            if (not isinstance(configured_root, str) or
                    os.path.normcase(os.path.abspath(configured_root)) !=
                    os.path.normcase(plugin_root)):
                raise RuntimeError("ANSA MCP config pointer targets another plugin root")
            return os.path.abspath(target)
    configured = os.environ.get("ANSA_MCP_BRIDGE_CONFIG", "").strip()
    if configured:
        return os.path.abspath(os.path.expanduser(configured))
    local = os.environ.get("LOCALAPPDATA", "").strip()
    if not local:
        local = os.path.join(os.path.expanduser("~"), "AppData", "Local")
    return os.path.join(local, "ANSAMCP", "bridge.json")


def _plugin_root():
    script_path = globals().get("__file__")
    if script_path:
        return os.path.dirname(os.path.abspath(script_path))
    config_path = _bridge_config_path()
    with open(config_path, "r", encoding="utf-8-sig") as stream:
        value = json.load(stream)
    configured = value.get("plugin_root") if isinstance(value, dict) else None
    if not isinstance(configured, str) or not configured.strip():
        raise RuntimeError(
            "ANSA load_script did not provide __file__ and bridge config has no plugin_root"
        )
    resolved = os.path.abspath(os.path.expanduser(configured))
    if not os.path.isdir(resolved):
        raise RuntimeError("Configured ANSA MCP plugin_root does not exist: " + resolved)
    return resolved


def _startup_error_path():
    directory = os.path.dirname(_bridge_config_path())
    return os.path.join(directory, "startup-error.log")


def _record_startup_error():
    try:
        path = _startup_error_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as stream:
            stream.write(
                "[{0}] ANSA MCP bridge startup failed\n{1}\n".format(
                    datetime.now(timezone.utc).isoformat(), traceback.format_exc()
                )
            )
        return path
    except Exception:
        return None


def main():
    # Make the same resolved path authoritative for the bridge package's
    # config loader, not just this wrapper's plugin-root/error-log lookup.
    os.environ["ANSA_MCP_BRIDGE_CONFIG"] = _bridge_config_path()
    plugin_root = _plugin_root()
    if plugin_root not in sys.path:
        sys.path.insert(0, plugin_root)
    from ansa_mcp_bridge import start

    return start()


try:
    START_RESULT = main()
except Exception:
    ERROR_LOG = _record_startup_error()
    if ERROR_LOG:
        print("ANSA MCP startup failed; details written to:", ERROR_LOG)
    else:
        print("ANSA MCP startup failed and the error log could not be written")
    raise
else:
    print("ANSA MCP start result:", START_RESULT)

