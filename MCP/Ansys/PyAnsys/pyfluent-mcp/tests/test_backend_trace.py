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

import logging

from ansys.fluent.mcp.common import backend_trace


def test_trace_call_disabled_by_default(monkeypatch, caplog):
    """Verify that trace call disabled by default.

    Parameters
    ----------
    monkeypatch : Any
        Pytest fixture used to patch environment variables or dependencies.
    caplog : Any
        Pytest fixture used to capture log records during the test.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    monkeypatch.delenv("FLUIDS_BACKEND_TRACE", raising=False)
    monkeypatch.setattr(backend_trace.logger, "disabled", False)
    caplog.set_level(logging.INFO, logger="ansys.fluent.mcp.backend_trace")

    backend_trace.trace_call("get_state", summary="paths=2")

    assert "backend_call" not in caplog.text


def test_trace_call_line_mode(monkeypatch, caplog):
    """Verify that trace call line mode.

    Parameters
    ----------
    monkeypatch : Any
        Pytest fixture used to patch environment variables or dependencies.
    caplog : Any
        Pytest fixture used to capture log records during the test.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    monkeypatch.setenv("FLUIDS_BACKEND_TRACE", "1")
    monkeypatch.setattr(backend_trace.logger, "disabled", False)
    caplog.set_level(logging.INFO, logger="ansys.fluent.mcp.backend_trace")

    backend_trace.trace_call("get_state", summary="paths=2")

    assert "backend_call method=get_state paths=2" in caplog.text
    assert "caller=" not in caplog.text


def test_trace_call_stack_mode_includes_caller(monkeypatch, caplog):
    """Verify that trace call stack mode includes caller.

    Parameters
    ----------
    monkeypatch : Any
        Pytest fixture used to patch environment variables or dependencies.
    caplog : Any
        Pytest fixture used to capture log records during the test.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    monkeypatch.setenv("FLUIDS_BACKEND_TRACE", "stack")
    monkeypatch.setattr(backend_trace.logger, "disabled", False)
    caplog.set_level(logging.INFO, logger="ansys.fluent.mcp.backend_trace")

    backend_trace.trace_call("run_code", summary="chars=12")

    assert "backend_call method=run_code chars=12 caller=" in caplog.text


def test_trace_call_swallows_logger_errors(monkeypatch):
    """Verify that trace call swallows logger errors.

    Parameters
    ----------
    monkeypatch : Any
        Pytest fixture used to patch environment variables or dependencies.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    monkeypatch.setenv("FLUIDS_BACKEND_TRACE", "on")

    def raise_from_info(*args, **kwargs):
        """Exercise the raise from info test helper.

        Parameters
        ----------
        args : Any
            Positional arguments forwarded to the callable.
        kwargs : Any
            Keyword arguments forwarded to the callable.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        raise RuntimeError("logging failed")

    monkeypatch.setattr(backend_trace.logger, "info", raise_from_info)

    backend_trace.trace_call("solver_status")
