# Copyright (C) 2026 Synopsys, Inc. and ANSYS, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

r"""Per-session debug logging for CFX-MCP.

When the gateway (or any long-running entry point) starts, this module
creates a per-session folder and attaches a DEBUG-level file handler to
this package's root logger (``ansys.cfx.mcp``). An optional
higher-level layer that shares the process can add its own root via
:func:`register_log_root` so a single ``session.log`` captures the whole
stack — this package never names or imports that layer. All child
loggers propagate up to the handler, so tool calls, plan executions,
run_code snippets, and validator decisions are all captured in one place
without touching individual call sites.

Goals
-----
* **Self-service diagnostics** — when a user reports a problem we can
  ask them to attach the session folder and have the full picture
  (logs, recorded tool args, last `run_code` snippets via the existing
  RunLogger, environment snapshot).
* **Off by default for embedded use** — the library import path stays
  silent. The handler is only attached when an entry point explicitly
  calls :func:`init_session_logging` (the gateway and the CLI both
  do).
* **Easy to disable** — setting ``FLUIDS_MCP_DISABLE_SESSION_LOGS=1``
  short-circuits the call. Safe in regulated environments where local
  log files must not be created.

Layout
------
Default base directory:

* Windows: ``%APPDATA%\\Ansys\\v271\\cfx\\aisol``
* macOS / Linux: ``~/.ansys/v271/cfx/aisol``

Override with ``FLUIDS_MCP_SESSION_LOG_DIR=<path>`` (the path is used
verbatim — sessions still get their own subfolders inside it).

Each session creates ``<base>/<session_id>/`` containing:

* ``session.log`` — DEBUG-level text log of every
    ``ansys.cfx.mcp.*`` module (plus any extra roots registered via
    :func:`register_log_root`) through Python's logging.
* ``env.txt`` — snapshot of process env vars relevant to the server
    (``FLUIDS_*``, ``ANSYS_*``, ``AWP_ROOT*``, ``AALI_*``) plus Python/OS
    versions.
* ``meta.json`` — small JSON file with session id, start time, log
    base, gateway host/port (if known).

Any embedding host may continue to write its own request-level logs separately;
the new session folder is for *cross-cutting* diagnostics, not host-level event
streams.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import platform
import sys
from typing import Optional
import uuid

logger = logging.getLogger("ansys.cfx.mcp.session_logging")

# Sentinel attribute used to recognise the file handler we attached, so
# repeated calls to ``init_session_logging`` are idempotent and don't
# duplicate handlers (e.g. when uvicorn reloads or when both the CLI
# entry point and the gateway code path call us).
_HANDLER_TAG = "_ansys_cfx_mcp_session_handler"
_HANDLER_DIR_ATTR = "_ansys_cfx_mcp_session_dir"

_LOG_FILENAME = "session.log"
_META_FILENAME = "meta.json"
_ENV_FILENAME = "env.txt"
# Stable pointer files written at the *base* dir so users always have a
# fixed path to copy from without needing to know the current session
# id. ``latest_session.txt`` contains the absolute session-dir path;
# ``latest.log`` is a best-effort copy/mirror of ``session.log``
# (refreshed on each event via a small handler — see _LatestMirror).
_LATEST_POINTER = "latest_session.txt"
_LATEST_LOG = "latest.log"

# Env-var names. Keep these in sync with ``common/config.py`` allow-list.
#
# Logging is ON by default for entry points that call
# :func:`init_session_logging` (the ``fluids-agent serve`` gateway).
# Set ``FLUIDS_MCP_DISABLE_SESSION_LOGS=1`` to opt out (regulated
# environments, sandboxed CI, etc.). ``FLUIDS_MCP_SESSION_LOGS=0`` is
# also honoured as a synonym for explicit disable.
ENV_ENABLE = "FLUIDS_MCP_SESSION_LOGS"
ENV_DISABLE = "FLUIDS_MCP_DISABLE_SESSION_LOGS"
ENV_BASE_DIR = "FLUIDS_MCP_SESSION_LOG_DIR"
ENV_LEVEL = "FLUIDS_MCP_SESSION_LOG_LEVEL"

# Root loggers we attach the session handler to. ``ansys.cfx.mcp``
# covers every module this package owns. An optional higher-level layer
# in the same process can add its own root via :func:`register_log_root`
# so a single ``session.log`` captures the whole stack. Roots are
# independent (none is an ancestor of another), and the per-record
# dedupe filter means attaching to multiple roots never double-logs.
# This is a mutable list, not a tuple, precisely so the registration
# hook can extend it without this package ever naming the consumer.
_OWNED_LOGGERS: list[str] = ["ansys.cfx.mcp"]
_OPTIONAL_DEBUG_LOGGERS: tuple[str, ...] = ("httpx",)
_ORIGINAL_GET_LOGGER = logging.getLogger
_ACTIVE_SESSION_LEVEL: int | None = None


def _is_owned_logger_name(name: str) -> bool:
    """Return whether owned logger name.

    Parameters
    ----------
    name : str
        Name of the object, module, or setting being processed.

    Returns
    -------
    bool
        Boolean result of the operation.
    """
    return any(name == root or name.startswith(root + ".") for root in _OWNED_LOGGERS)


def _session_get_logger(name: str | None = None) -> logging.Logger:
    """Return the logger for the active session context.

    Parameters
    ----------
    name : str | None
        Name of the object, module, or setting being processed.

    Returns
    -------
    logging.Logger
        logging.Logger produced by the operation.
    """
    got = _ORIGINAL_GET_LOGGER(name)
    if isinstance(name, str) and _ACTIVE_SESSION_LEVEL is not None and _is_owned_logger_name(name):
        got.disabled = False
        if name in _OWNED_LOGGERS and (
            got.level == logging.NOTSET or got.level > _ACTIVE_SESSION_LEVEL
        ):
            got.setLevel(_ACTIVE_SESSION_LEVEL)
    return got


def _install_session_get_logger(level: int) -> None:
    """Install the session-aware logger lookup hook.

    Parameters
    ----------
    level : int
        Logging level or severity to apply.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    global _ACTIVE_SESSION_LEVEL
    _ACTIVE_SESSION_LEVEL = level
    if logging.getLogger is not _session_get_logger:
        logging.getLogger = _session_get_logger


def _remove_session_get_logger() -> None:
    """Remove session get logger.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    global _ACTIVE_SESSION_LEVEL
    _ACTIVE_SESSION_LEVEL = None
    if logging.getLogger is _session_get_logger:
        logging.getLogger = _ORIGINAL_GET_LOGGER


def _owned_loggers() -> list[logging.Logger]:
    """Return logger names owned by this package.

    Returns
    -------
    list[logging.Logger]
        List of results produced by the operation.
    """
    return [_ORIGINAL_GET_LOGGER(name) for name in _OWNED_LOGGERS]


def _iter_known_loggers() -> list[logging.Logger]:
    """Iterate over loggers known to the logging manager.

    Returns
    -------
    list[logging.Logger]
        List of results produced by the operation.
    """
    loggers = [_ORIGINAL_GET_LOGGER()]
    for item in logging.root.manager.loggerDict.values():
        if isinstance(item, logging.Logger):
            loggers.append(item)
    return loggers


def _enable_logger_tree(root_name: str, *, level: int | None = None) -> None:
    """Enable logging for the package logger tree.

    Parameters
    ----------
    root_name : str
        Root name supplied to the function.
    level : int | None
        Logging level or severity to apply.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    root_logger = _ORIGINAL_GET_LOGGER(root_name)
    root_logger.disabled = False
    if level is not None and (root_logger.level == logging.NOTSET or root_logger.level > level):
        root_logger.setLevel(level)
    for name, item in logging.root.manager.loggerDict.items():
        if name == root_name or name.startswith(root_name + "."):
            if isinstance(item, logging.Logger):
                item.disabled = False


def register_log_root(name: str) -> None:
    """Register an extra logger root for the session file handler.

    Inversion-of-control hook: a higher-level layer running in the same
    process (e.g. an agent product with its own top-level package logger)
    calls this at import time to have its records captured in the same
    ``session.log`` — without this package ever importing or naming that
    layer. Idempotent. If a session handler is already attached, the new
    root is wired up immediately so registration order does not matter.

    Parameters
    ----------
    name : str
        Name of the object, module, or setting being processed.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    if not name or name in _OWNED_LOGGERS:
        return
    _OWNED_LOGGERS.append(name)
    _enable_logger_tree(name)
    target = _ORIGINAL_GET_LOGGER(name)
    # If logging is already live, attach every existing session handler
    # (main + latest mirror) to the newly registered root and make sure
    # it lets records through to them.
    attached_level: int | None = None
    for owned in _owned_loggers():
        for handler in owned.handlers:
            if getattr(handler, _HANDLER_TAG, False):
                if handler not in target.handlers:
                    target.addHandler(handler)
                attached_level = handler.level
    if attached_level is not None:
        if target.level == logging.NOTSET or target.level > attached_level:
            target.setLevel(attached_level)
        target.propagate = True


class _OncePerRecordFilter(logging.Filter):
    """Drop a record the second time the *same* handler sees it.

    The session FileHandler is attached at several points in the logger
    hierarchy (our owned roots plus optional external roots). Tagging
    the record on first emit makes the handler idempotent regardless of
    hierarchy.
    """

    _ATTR = "_ansys_cfx_mcp_session_emitted"

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003
        """Filter log records for the active session context.

        Parameters
        ----------
        record : logging.LogRecord
            Record supplied to the function.

        Returns
        -------
        bool
            Boolean result of the operation.
        """
        if getattr(record, self._ATTR, False):
            return False
        setattr(record, self._ATTR, True)
        return True


def _find_session_handler_dir() -> Optional[Path]:
    """Return the session dir from an already-attached handler, if any.

    Returns
    -------
    Optional[Path]
        Result produced by the function.
    """
    for owned in _owned_loggers():
        for handler in owned.handlers:
            if getattr(handler, _HANDLER_TAG, False):
                existing = getattr(handler, _HANDLER_DIR_ATTR, None)
                if isinstance(existing, Path):
                    return existing
    return None


def _truthy(name: str) -> bool:
    """Return whether the text represents an enabled value.

    Parameters
    ----------
    name : str
        Name of the object, module, or setting being processed.

    Returns
    -------
    bool
        Boolean result of the operation.
    """
    return os.environ.get(name, "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _is_disabled() -> bool:
    # Enabled by default. Explicit disable wins. We honour both
    # ``FLUIDS_MCP_DISABLE_SESSION_LOGS=1`` and the falsy values of
    # ``FLUIDS_MCP_SESSION_LOGS`` (``0`` / ``false`` / ``off``).
    """Return whether disabled.

    Returns
    -------
    bool
        Boolean result of the operation.
    """
    if _truthy(ENV_DISABLE):
        return True
    raw = os.environ.get(ENV_ENABLE, "").strip().lower()
    if raw in {"0", "false", "no", "off"}:
        return True
    return False


def _resolve_base_dir() -> Path:
    """Pick the base directory for all session folders.

    Override priority: ``FLUIDS_MCP_SESSION_LOG_DIR`` > APPDATA on
    Windows > ``~/.ansys`` elsewhere.

    Returns
    -------
    Path
        Result produced by the function.
    """
    override = os.environ.get(ENV_BASE_DIR)
    if override:
        return Path(override).expanduser().resolve()
    if os.name == "nt":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata).resolve() / "Ansys" / "v271" / "cfx" / "aisol"
    return Path.home() / ".ansys" / "v271" / "cfx" / "aisol"


def _new_session_id() -> str:
    """Create a new session identifier.

    Returns
    -------
    str
        String value produced by the helper.
    """
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return f"{ts}-{uuid.uuid4().hex[:8]}"


def _resolve_level() -> int:
    """Resolve level.

    Returns
    -------
    int
        Configured integer limit used by the helper.
    """
    raw = os.environ.get(ENV_LEVEL, "DEBUG").strip().upper()
    return getattr(logging, raw, logging.DEBUG)


def _gather_env_snapshot() -> str:
    """Render the relevant env vars + interpreter info as plain text.

    Returns
    -------
    str
        String result produced by the function.
    """
    keep_prefixes = ("FLUIDS_", "ANSYS", "AWP_ROOT", "AALI_")
    redact_keys = ("API_KEY", "TOKEN", "SECRET", "PASSWORD")
    lines: list[str] = []
    lines.append(f"# Captured: {datetime.now(timezone.utc).isoformat()}")
    lines.append(f"python: {sys.version.split()[0]}")
    lines.append(f"platform: {platform.platform()}")
    lines.append("")
    lines.append("# Environment variables")
    for key in sorted(os.environ):
        if not any(key.startswith(p) for p in keep_prefixes):
            continue
        value = os.environ[key]
        if any(redacted in key.upper() for redacted in redact_keys) and value:
            value = f"<redacted len={len(value)}>"
        lines.append(f"{key}={value}")
    return "\n".join(lines) + "\n"


def init_session_logging(
    *,
    session_id: Optional[str] = None,
    extra_meta: Optional[dict[str, object]] = None,
) -> Optional[Path]:
    """Set up a session log folder and attach a file handler.

    Returns the resolved session directory, or ``None`` when disabled
    via :data:`ENV_DISABLE`. Safe to call multiple times — subsequent
    calls return the existing directory without re-attaching handlers.

    Parameters
    ----------
    session_id : Optional[str]
        Session id supplied to the function.
    extra_meta : Optional[dict[str, object]]
        Extra meta supplied to the function.

    Returns
    -------
    Optional[Path]
        Result produced by the function.
    """
    if _is_disabled():
        return None

    existing_dir = _find_session_handler_dir()
    if existing_dir is not None:
        return existing_dir

    base_dir = _resolve_base_dir()
    sid = session_id or _new_session_id()
    session_dir = base_dir / sid
    try:
        session_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        # Log to whatever handlers exist already, but do not fail the
        # caller — diagnostics are best-effort.
        logger.warning("Could not create session log dir %s: %s", session_dir, exc)
        return None

    log_path = session_dir / _LOG_FILENAME
    level = _resolve_level()
    _install_session_get_logger(level)

    try:
        handler = logging.FileHandler(log_path, encoding="utf-8", delay=True)
    except OSError as exc:
        logger.warning("Could not open session log file %s: %s", log_path, exc)
        return None
    handler.setLevel(level)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s: %(message)s",
        ),
    )
    # The main handler can be attached at several hierarchy levels;
    # dedupe so a single record is never written twice.
    handler.addFilter(_OncePerRecordFilter())
    setattr(handler, _HANDLER_TAG, True)
    setattr(handler, _HANDLER_DIR_ATTR, session_dir)
    owned_loggers = _owned_loggers()
    for owned in owned_loggers:
        owned.addHandler(handler)

    # Mirror handler at <base>/latest.log so the user has a stable path
    # to copy from without knowing the current session id. We truncate
    # the file on init so its content always matches the *current*
    # session (not a concatenation of past sessions).
    latest_log_path = base_dir / _LATEST_LOG
    try:
        # Truncate / create empty so this session starts fresh.
        latest_log_path.write_text("", encoding="utf-8")
        latest_handler = logging.FileHandler(
            latest_log_path,
            encoding="utf-8",
            delay=True,
        )
    except OSError as exc:
        logger.warning("Could not open latest.log mirror %s: %s", latest_log_path, exc)
        latest_handler = None
    if latest_handler is not None:
        latest_handler.setLevel(level)
        latest_handler.setFormatter(handler.formatter)
        setattr(latest_handler, _HANDLER_TAG, True)
        setattr(latest_handler, _HANDLER_DIR_ATTR, session_dir)
        for owned in owned_loggers:
            owned.addHandler(latest_handler)

    # Stable pointer file at the base so a CLI tool / user can find
    # the active session without listing directories.
    try:
        (base_dir / _LATEST_POINTER).write_text(
            str(session_dir) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        logger.warning("Could not write latest_session pointer: %s", exc)
    # Make sure the package loggers let DEBUG records through; without
    # this the per-module .info()/.debug() calls would be filtered
    # before reaching our handler even though the handler accepts them.
    for owned in owned_loggers:
        if owned.level == logging.NOTSET or owned.level > level:
            owned.setLevel(level)
        _enable_logger_tree(owned.name, level=level)
        owned.propagate = True

    # Optional: attach the same handler to a few well-known external
    # loggers so HTTP transport output lands in the same file when the
    # user sets FLUIDS_MCP_SESSION_LOG_LEVEL=DEBUG.
    for ext_name in _OPTIONAL_DEBUG_LOGGERS:
        ext_logger = _ORIGINAL_GET_LOGGER(ext_name)
        # Don't change the external logger's level (avoid surprising
        # callers); just add our handler so existing records flow in.
        if not any(getattr(h, _HANDLER_TAG, False) for h in ext_logger.handlers):
            ext_logger.addHandler(handler)

    # Drop the env snapshot first so users have something to attach
    # even if the log file ends up empty.
    try:
        (session_dir / _ENV_FILENAME).write_text(
            _gather_env_snapshot(),
            encoding="utf-8",
        )
    except OSError as exc:
        logger.warning("Could not write env snapshot: %s", exc)

    meta: dict[str, object] = {
        "session_id": sid,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "session_dir": str(session_dir),
        "log_file": str(log_path),
        "log_level": logging.getLevelName(level),
        "pid": os.getpid(),
    }
    if extra_meta:
        meta.update(extra_meta)
    try:
        (session_dir / _META_FILENAME).write_text(
            json.dumps(meta, indent=2, default=str),
            encoding="utf-8",
        )
    except OSError as exc:
        logger.warning("Could not write session meta: %s", exc)

    logger.info(
        "Session logging enabled: dir=%s level=%s (disable with %s=1)",
        session_dir,
        logging.getLevelName(level),
        ENV_DISABLE,
    )
    return session_dir


def get_session_log_dir() -> Optional[Path]:
    """Return the active session log directory, if any.

    Returns
    -------
    Optional[Path]
        Result produced by the function.
    """
    return _find_session_handler_dir()


def get_latest_log_path() -> Optional[Path]:
    """Return the path to ``<base>/latest.log`` if it exists.

    This is the stable pointer the user can ``Get-Content`` / ``tail``
    without needing to know the session id. Returns ``None`` if
    session logging has never run on this machine.

    Returns
    -------
    Optional[Path]
        Result produced by the function.
    """
    # Prefer the live in-process handler when available.
    active_dir = get_session_log_dir()
    if active_dir is not None:
        candidate = active_dir.parent / _LATEST_LOG
        if candidate.exists():
            return candidate
    # Fallback: probe the default base dir without initialising logging.
    base = _resolve_base_dir()
    candidate = base / _LATEST_LOG
    return candidate if candidate.exists() else None


def get_latest_session_dir() -> Optional[Path]:
    """Return the path from ``<base>/latest_session.txt``, if present.

    Use this from a separate process (e.g. a CLI command) to find the
    most recent ``serve`` session directory without scanning timestamps.

    Returns
    -------
    Optional[Path]
        Result produced by the function.
    """
    base = _resolve_base_dir()
    pointer = base / _LATEST_POINTER
    if not pointer.exists():
        return None
    try:
        raw = pointer.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not raw:
        return None
    path = Path(raw)
    return path if path.exists() else None


def shutdown_session_logging() -> None:
    """Detach and close the session file handler.

    Used by tests; in production the handler outlives the process by design.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    handlers_to_close: dict[int, logging.Handler] = {}
    for known_logger in _iter_known_loggers():
        to_remove = [h for h in known_logger.handlers if getattr(h, _HANDLER_TAG, False)]
        for handler in to_remove:
            known_logger.removeHandler(handler)
            handlers_to_close[id(handler)] = handler
    for handler in handlers_to_close.values():
        try:
            handler.close()
        except Exception as exc:
            logger.warning("Failed to close session log handler cleanly: %s", exc)
    _remove_session_get_logger()


__all__ = [
    "ENV_BASE_DIR",
    "ENV_DISABLE",
    "ENV_ENABLE",
    "ENV_LEVEL",
    "get_latest_log_path",
    "get_latest_session_dir",
    "get_session_log_dir",
    "init_session_logging",
    "register_log_root",
    "shutdown_session_logging",
]
