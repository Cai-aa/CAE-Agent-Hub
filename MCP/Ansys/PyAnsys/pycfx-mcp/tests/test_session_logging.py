# Copyright (C) 2026 Synopsys, Inc. and ANSYS, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Coverage tests for session logging utilities."""

from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import patch

import pytest

from ansys.cfx.mcp.common import session_logging
from ansys.cfx.mcp.common.session_logging import (
    _HANDLER_TAG,
    ENV_ENABLE,
    _find_session_handler_dir,
    _gather_env_snapshot,
    _install_session_get_logger,
    _is_disabled,
    _iter_known_loggers,
    _new_session_id,
    _OncePerRecordFilter,
    _owned_loggers,
    _remove_session_get_logger,
    _resolve_base_dir,
    _resolve_level,
    _session_get_logger,
    _truthy,
    get_latest_log_path,
    get_latest_session_dir,
    get_session_log_dir,
    init_session_logging,
    register_log_root,
    shutdown_session_logging,
)


@pytest.fixture(autouse=True)
def cleanup_logging() -> None:
    """Ensure session logging state is reset between tests."""
    shutdown_session_logging()
    yield
    shutdown_session_logging()


@pytest.mark.unit
def test_truthy_environment_detection(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify truthy environment parsing."""
    monkeypatch.setenv("FLAG", "true")

    assert _truthy("FLAG") is True


@pytest.mark.unit
def test_is_disabled_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify disable switches are honored."""
    monkeypatch.setenv(session_logging.ENV_DISABLE, "1")

    assert _is_disabled() is True


@pytest.mark.unit
def test_is_disabled_from_enable_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify explicit disable values through enable env var."""
    monkeypatch.setenv(ENV_ENABLE, "off")

    assert _is_disabled() is True


@pytest.mark.unit
def test_resolve_base_dir_override(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Verify explicit base-directory overrides are used."""
    monkeypatch.setenv(session_logging.ENV_BASE_DIR, str(tmp_path))

    assert _resolve_base_dir() == tmp_path.resolve()


@pytest.mark.unit
def test_new_session_id_contains_separator() -> None:
    """Verify generated session identifiers are timestamped."""
    session_id = _new_session_id()

    assert "-" in session_id


@pytest.mark.unit
def test_resolve_level_defaults_to_debug(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify invalid log levels fall back to DEBUG."""
    monkeypatch.setenv(session_logging.ENV_LEVEL, "invalid")

    assert _resolve_level() == logging.DEBUG


@pytest.mark.unit
def test_resolve_level_accepts_named_level(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify known log-level names resolve correctly."""
    monkeypatch.setenv(session_logging.ENV_LEVEL, "warning")

    assert _resolve_level() == logging.WARNING


@pytest.mark.unit
def test_gather_env_snapshot_redacts_sensitive_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify environment snapshots redact secrets."""
    monkeypatch.setenv("FLUIDS_API_KEY", "secret-value")

    snapshot = _gather_env_snapshot()

    assert "<redacted" in snapshot


@pytest.mark.unit
def test_once_per_record_filter_deduplicates() -> None:
    """Verify duplicate records are filtered."""
    record = logging.LogRecord(
        name="demo",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="message",
        args=(),
        exc_info=None,
    )

    filter_ = _OncePerRecordFilter()

    assert filter_.filter(record) is True
    assert filter_.filter(record) is False


@pytest.mark.unit
def test_init_session_logging_creates_artifacts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Verify session logging initialization creates expected files."""
    monkeypatch.setenv(session_logging.ENV_BASE_DIR, str(tmp_path))

    session_dir = init_session_logging(session_id="demo-session")

    assert session_dir is not None
    assert (session_dir / "env.txt").exists()
    assert (session_dir / "meta.json").exists()
    assert get_session_log_dir() == session_dir
    assert _find_session_handler_dir() == session_dir


@pytest.mark.unit
def test_init_session_logging_is_idempotent(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Verify repeated initialization reuses the same session."""
    monkeypatch.setenv(session_logging.ENV_BASE_DIR, str(tmp_path))

    first = init_session_logging(session_id="one")
    second = init_session_logging(session_id="two")

    assert first == second


@pytest.mark.unit
def test_register_log_root_adds_logger_handler(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Verify late logger registration attaches session handlers."""
    monkeypatch.setenv(session_logging.ENV_BASE_DIR, str(tmp_path))

    init_session_logging(session_id="demo")
    register_log_root("custom.logger")

    logger = logging.getLogger("custom.logger")
    session_handlers = [
        handler for handler in logger.handlers if getattr(handler, _HANDLER_TAG, False)
    ]

    assert logger.propagate is True
    assert len(session_handlers) == 2
    assert all(handler.level == logging.DEBUG for handler in session_handlers)


@pytest.mark.unit
def test_register_log_root_ignores_duplicates() -> None:
    """Verify duplicate logger registrations are ignored."""
    register_log_root("custom.duplicate")

    before = list(_owned_loggers())

    register_log_root("")
    register_log_root("custom.duplicate")

    after = list(_owned_loggers())

    assert len(before) == len(after)


@pytest.mark.unit
def test_get_latest_paths(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Verify latest-session helper paths resolve correctly."""
    monkeypatch.setenv(session_logging.ENV_BASE_DIR, str(tmp_path))

    session_dir = init_session_logging(session_id="latest-demo")

    latest_log = get_latest_log_path()
    latest_session = get_latest_session_dir()

    assert latest_log is not None
    assert latest_log.exists()
    assert latest_session == session_dir


@pytest.mark.unit
def test_get_latest_session_dir_handles_invalid_pointer(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Verify invalid pointer targets are ignored."""
    monkeypatch.setenv(session_logging.ENV_BASE_DIR, str(tmp_path))

    pointer = tmp_path / "latest_session.txt"
    pointer.write_text(str(tmp_path / "missing"), encoding="utf-8")

    assert get_latest_session_dir() is None


@pytest.mark.unit
def test_get_latest_log_path_without_active_session(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Verify fallback latest-log discovery."""
    monkeypatch.setenv(session_logging.ENV_BASE_DIR, str(tmp_path))

    latest = tmp_path / "latest.log"
    latest.write_text("demo", encoding="utf-8")

    assert get_latest_log_path() == latest


@pytest.mark.unit
def test_install_and_remove_session_get_logger() -> None:
    """Verify logger hook install and removal."""
    _install_session_get_logger(logging.INFO)

    assert logging.getLogger is _session_get_logger

    _remove_session_get_logger()

    assert logging.getLogger is not _session_get_logger


@pytest.mark.unit
def test_iter_known_loggers_returns_root_logger() -> None:
    """Verify logger iteration includes root logger."""
    loggers = _iter_known_loggers()

    assert any(logger.name == "root" for logger in loggers)


@pytest.mark.unit
def test_init_session_logging_handles_directory_creation_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Verify directory creation failures are tolerated."""
    monkeypatch.setenv(session_logging.ENV_BASE_DIR, str(tmp_path))

    with patch.object(Path, "mkdir", side_effect=OSError("boom")):
        result = init_session_logging(session_id="broken")

    assert result is None


@pytest.mark.unit
def test_shutdown_session_logging_removes_handlers(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Verify session logging shutdown detaches handlers."""
    monkeypatch.setenv(session_logging.ENV_BASE_DIR, str(tmp_path))

    init_session_logging(session_id="shutdown-demo")

    assert get_session_log_dir() is not None

    shutdown_session_logging()

    assert get_session_log_dir() is None
