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

import builtins
import json
import logging

from ansys.fluent.mcp.common import session_logging


def _cleanup_session_logging():
    """Exercise the cleanup session logging test helper.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    session_logging.shutdown_session_logging()
    session_logging._OWNED_LOGGERS[:] = ["ansys.fluent.mcp", "fluids_mcp"]


def test_session_logging_env_helpers(monkeypatch, tmp_path):
    """Verify that session logging env helpers.

    Parameters
    ----------
    monkeypatch : Any
        Pytest fixture used to patch environment variables or dependencies.
    tmp_path : Any
        Path for the tmp.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    monkeypatch.delenv(session_logging.ENV_DISABLE, raising=False)
    monkeypatch.delenv(session_logging.ENV_ENABLE, raising=False)
    monkeypatch.delenv(session_logging.ENV_BASE_DIR, raising=False)
    monkeypatch.delenv(session_logging.ENV_LEVEL, raising=False)

    assert session_logging._truthy(session_logging.ENV_DISABLE) is False
    assert session_logging._is_disabled() is False

    monkeypatch.setenv(session_logging.ENV_DISABLE, "yes")
    assert session_logging._truthy(session_logging.ENV_DISABLE) is True
    assert session_logging._is_disabled() is True

    monkeypatch.setenv(session_logging.ENV_DISABLE, "0")
    monkeypatch.setenv(session_logging.ENV_ENABLE, "off")
    assert session_logging._is_disabled() is True

    monkeypatch.setenv(session_logging.ENV_ENABLE, "1")
    monkeypatch.setenv(session_logging.ENV_BASE_DIR, str(tmp_path / "logs"))
    monkeypatch.setenv(session_logging.ENV_LEVEL, "INFO")

    assert session_logging._resolve_base_dir() == (tmp_path / "logs").resolve()
    assert session_logging._resolve_level() == logging.INFO

    monkeypatch.setenv(session_logging.ENV_LEVEL, "not-a-level")
    assert session_logging._resolve_level() == logging.DEBUG


def test_env_snapshot_filters_and_redacts(monkeypatch):
    """Verify that env snapshot filters and redacts.

    Parameters
    ----------
    monkeypatch : Any
        Pytest fixture used to patch environment variables or dependencies.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    monkeypatch.setenv("FLUIDS_VISIBLE", "value")
    monkeypatch.setenv("FLUIDS_API_KEY", "abcdef")
    monkeypatch.setenv("ANSYS_TOKEN", "secret-token")
    monkeypatch.setenv("UNRELATED_SECRET", "should-not-appear")

    snapshot = session_logging._gather_env_snapshot()

    assert "FLUIDS_VISIBLE=value" in snapshot
    assert "FLUIDS_API_KEY=<redacted len=6>" in snapshot
    assert "ANSYS_TOKEN=<redacted len=12>" in snapshot
    assert "UNRELATED_SECRET" not in snapshot
    assert "pyfluent:" in snapshot


def test_env_snapshot_uses_package_metadata_without_importing_pyfluent(monkeypatch):
    """Verify that env snapshot reads PyFluent version without importing PyFluent.

    Parameters
    ----------
    monkeypatch : Any
        Pytest fixture used to patch environment variables or dependencies.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    calls = []

    def fake_version(name):
        calls.append(name)
        return "1.2.3"

    real_import = builtins.__import__

    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "ansys.fluent.core" or name.startswith("ansys.fluent.core."):
            raise AssertionError("env snapshot must not import ansys.fluent.core")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(session_logging, "version", fake_version)
    monkeypatch.setattr(builtins, "__import__", guarded_import)

    snapshot = session_logging._gather_env_snapshot()

    assert calls == ["ansys-fluent-core"]
    assert "pyfluent: 1.2.3" in snapshot


def test_env_snapshot_handles_missing_pyfluent_distribution(monkeypatch):
    """Verify that env snapshot handles missing PyFluent distribution metadata.

    Parameters
    ----------
    monkeypatch : Any
        Pytest fixture used to patch environment variables or dependencies.

    Returns
    -------
    None
        The function completes through its side effects.
    """

    def missing_version(name):
        raise session_logging.PackageNotFoundError(name)

    monkeypatch.setattr(session_logging, "version", missing_version)

    snapshot = session_logging._gather_env_snapshot()

    assert "pyfluent: <not installed>" in snapshot


def test_init_session_logging_creates_artifacts_and_is_idempotent(monkeypatch, tmp_path):
    """Verify that init session logging creates artifacts and is idempotent.

    Parameters
    ----------
    monkeypatch : Any
        Pytest fixture used to patch environment variables or dependencies.
    tmp_path : Any
        Path for the tmp.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    _cleanup_session_logging()
    monkeypatch.setenv(session_logging.ENV_BASE_DIR, str(tmp_path))
    monkeypatch.setenv(session_logging.ENV_LEVEL, "INFO")
    monkeypatch.delenv(session_logging.ENV_DISABLE, raising=False)
    monkeypatch.delenv(session_logging.ENV_ENABLE, raising=False)

    try:
        session_dir = session_logging.init_session_logging(
            session_id="test-session",
            extra_meta={"host": "localhost", "port": 5000},
        )
        again = session_logging.init_session_logging(session_id="ignored")
        log = logging.getLogger("ansys.fluent.mcp.tests.session_logging")
        log.info("hello from session logging test")
    finally:
        session_logging.shutdown_session_logging()

    assert session_dir == tmp_path / "test-session"
    assert again == session_dir
    assert session_logging.get_session_log_dir() is None
    assert (session_dir / "env.txt").is_file()
    assert (session_dir / "session.log").read_text(encoding="utf-8").count(
        "hello from session logging test"
    ) == 1
    assert (tmp_path / "latest.log").read_text(encoding="utf-8").count(
        "hello from session logging test"
    ) == 1
    assert (tmp_path / "latest_session.txt").read_text(encoding="utf-8").strip() == str(session_dir)

    meta = json.loads((session_dir / "meta.json").read_text(encoding="utf-8"))
    assert meta["session_id"] == "test-session"
    assert meta["log_level"] == "INFO"
    assert meta["host"] == "localhost"
    assert meta["port"] == 5000
    assert session_logging.get_latest_log_path() == tmp_path / "latest.log"
    assert session_logging.get_latest_session_dir() == session_dir


def test_disabled_init_and_empty_latest_pointer(monkeypatch, tmp_path):
    """Verify that disabled init and empty latest pointer.

    Parameters
    ----------
    monkeypatch : Any
        Pytest fixture used to patch environment variables or dependencies.
    tmp_path : Any
        Path for the tmp.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    _cleanup_session_logging()
    monkeypatch.setenv(session_logging.ENV_BASE_DIR, str(tmp_path))
    monkeypatch.setenv(session_logging.ENV_DISABLE, "1")

    assert session_logging.init_session_logging(session_id="disabled") is None
    assert not (tmp_path / "disabled").exists()

    monkeypatch.setenv(session_logging.ENV_DISABLE, "0")
    (tmp_path / "latest_session.txt").write_text("\n", encoding="utf-8")
    assert session_logging.get_latest_session_dir() is None
    assert session_logging.get_latest_log_path() is None


def test_register_log_root_after_init_attaches_active_handlers(monkeypatch, tmp_path):
    """Verify that register log root after init attaches active handlers.

    Parameters
    ----------
    monkeypatch : Any
        Pytest fixture used to patch environment variables or dependencies.
    tmp_path : Any
        Path for the tmp.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    _cleanup_session_logging()
    monkeypatch.setenv(session_logging.ENV_BASE_DIR, str(tmp_path))
    monkeypatch.setenv(session_logging.ENV_LEVEL, "DEBUG")

    try:
        session_dir = session_logging.init_session_logging(session_id="with-extra-root")
        session_logging.register_log_root("external.product")
        logging.getLogger("external.product.module").debug("external debug message")
        session_logging.register_log_root("external.product")
    finally:
        session_logging.shutdown_session_logging()
        session_logging._OWNED_LOGGERS[:] = ["ansys.fluent.mcp", "fluids_mcp"]

    text = (session_dir / "session.log").read_text(encoding="utf-8")
    assert "external debug message" in text
    assert session_logging._OWNED_LOGGERS == ["ansys.fluent.mcp", "fluids_mcp"]


def test_shutdown_removes_handlers_after_registered_roots_reset(monkeypatch, tmp_path):
    """Verify that shutdown removes handlers after registered roots reset.

    Parameters
    ----------
    monkeypatch : Any
        Pytest fixture used to patch environment variables or dependencies.
    tmp_path : Any
        Path for the tmp.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    _cleanup_session_logging()
    monkeypatch.setenv(session_logging.ENV_BASE_DIR, str(tmp_path))
    external = logging.getLogger("external.reset")

    try:
        session_logging.init_session_logging(session_id="reset-before-shutdown")
        session_logging.register_log_root("external.reset")
        assert any(
            getattr(handler, session_logging._HANDLER_TAG, False) for handler in external.handlers
        )

        session_logging._OWNED_LOGGERS[:] = ["ansys.fluent.mcp", "fluids_mcp"]
        session_logging.shutdown_session_logging()

        assert not any(
            getattr(handler, session_logging._HANDLER_TAG, False) for handler in external.handlers
        )
    finally:
        session_logging.shutdown_session_logging()
        session_logging._OWNED_LOGGERS[:] = ["ansys.fluent.mcp", "fluids_mcp"]
