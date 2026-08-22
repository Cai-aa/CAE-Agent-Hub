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

"""Smoke tests for the public ansys-fluent-mcp package.

Offline-only: no live Fluent, no network. These guard the import surface,
the bundled schema data, and the TLS security defaults.
"""

from __future__ import annotations

import importlib

import pytest


def test_package_imports():
    """Core modules import without optional heavy dependencies.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    importlib.import_module("ansys.fluent.mcp.common.network")
    importlib.import_module("ansys.fluent.mcp.solve.catalog.retriever")


def test_module_launcher_entry_point():
    """Console script resolves through ansys.fluent.mcp.__main__:launcher.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    from ansys.fluent.mcp.server import launcher, run_solve

    assert launcher is run_solve


def test_bundled_skill_present():
    """The Solve leaf SKILL.md ships as package data (installer reads it).

    Returns
    -------
    None
        The function completes through its side effects.
    """
    from importlib.resources import files

    skill = files("ansys.fluent.mcp.solve.skills").joinpath("SKILL.md")
    assert skill.is_file()


# --- TLS defaults (regression for the verify=False fix) -------------------


def test_tls_verify_on_by_default(monkeypatch):
    """Verify that tls verify on by default.

    Parameters
    ----------
    monkeypatch : Any
        Pytest fixture used to patch environment variables or dependencies.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    from ansys.fluent.mcp.common.network import resolve_tls_verify

    for var in (
        "FLUIDS_MCP_VERIFY_TLS",
        "FLUIDS_MCP_CA_BUNDLE",
        "SSL_CERT_FILE",
        "REQUESTS_CA_BUNDLE",
    ):
        monkeypatch.delenv(var, raising=False)
    assert resolve_tls_verify() is True


def test_tls_ca_bundle_path(monkeypatch):
    """Verify that tls ca bundle path.

    Parameters
    ----------
    monkeypatch : Any
        Pytest fixture used to patch environment variables or dependencies.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    from ansys.fluent.mcp.common.network import resolve_tls_verify

    monkeypatch.delenv("FLUIDS_MCP_VERIFY_TLS", raising=False)
    monkeypatch.setenv("FLUIDS_MCP_CA_BUNDLE", "/etc/ssl/corp-ca.pem")
    assert resolve_tls_verify() == "/etc/ssl/corp-ca.pem"


def test_tls_insecure_opt_out(monkeypatch):
    """Verify that tls insecure opt out.

    Parameters
    ----------
    monkeypatch : Any
        Pytest fixture used to patch environment variables or dependencies.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    from ansys.fluent.mcp.common.network import resolve_tls_verify

    monkeypatch.setenv("FLUIDS_MCP_VERIFY_TLS", "false")
    assert resolve_tls_verify() is False


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
