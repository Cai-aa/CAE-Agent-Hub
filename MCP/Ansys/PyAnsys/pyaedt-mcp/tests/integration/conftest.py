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

"""Integration test fixtures for real AEDT system runs."""

from pathlib import Path
import shutil

import pytest


def _configure_live_settings() -> None:
    try:
        from ansys.aedt.core import settings
    except Exception:
        from ansys.aedt.core.generic.settings import settings

    settings.use_grpc_api = True
    settings.release_on_exception = False


def _start_desktop_session():
    from ansys.aedt.core import Desktop

    _configure_live_settings()

    desktop = Desktop(non_graphical=True, new_desktop=True)
    if getattr(desktop, "port", None) is None:
        try:
            desktop.release_desktop(close_projects=False)
        except Exception:
            pass
        pytest.skip("Launched AEDT session did not expose a gRPC port.")

    return desktop


@pytest.fixture(scope="session")
def integration_tmp_root(tmp_path_factory):
    """Create and clean up the root directory for integration test artifacts."""
    root = tmp_path_factory.mktemp("integration-")
    yield root
    shutil.rmtree(root, ignore_errors=True)


@pytest.fixture(scope="session")
def desktop_session():
    """Launch one real AEDT Desktop for the integration test session."""
    desktop = _start_desktop_session()
    try:
        yield desktop
    finally:
        try:
            desktop.release_desktop(close_projects=False)
        except Exception:
            pass


@pytest.fixture
def test_tmp_dir(integration_tmp_root, request):
    """Create a per-test artifact directory under the integration root."""
    temp_dir = Path(integration_tmp_root) / request.node.name.split("[", 1)[0]
    if temp_dir.exists():
        shutil.rmtree(temp_dir, ignore_errors=True)
    temp_dir.mkdir(parents=True, exist_ok=True)
    return temp_dir
