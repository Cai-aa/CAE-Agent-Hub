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

"""Shared pytest fixtures and local-environment shims."""

import pytest


@pytest.fixture(scope="session", autouse=True)
def _patch_pyfluent_local_launch():
    """Work around a missing ``start_container`` global in some PyFluent builds.

    ansys-fluent-core 0.38.1's ``launch_fluent`` references a
    ``start_container`` name that is absent from its own signature, so a
    local (non-container) launch raises ``NameError: name 'start_container'
    is not defined`` before it ever reaches the standalone launcher.

    On GitHub Actions the integration tests run against the managed Fluent
    container (``PYFLUENT_LAUNCH_CONTAINER=1``) and never hit this path, so
    this shim is a no-op there. Locally, where Fluent is installed natively,
    we define the missing module global as ``None`` so PyFluent falls back to
    its env-var / ``container_dict`` launch-mode detection. The patch is only
    applied when the attribute is genuinely missing, so a fixed PyFluent build
    is left untouched.

    Returns
    -------
    Any
        Result produced by the function.
    """
    try:
        from ansys.fluent.core.launcher import launcher as _launcher
    except ImportError:
        # PyFluent not installed; integration tests will skip on their own.
        yield
        return

    patched = False
    if not hasattr(_launcher, "start_container"):
        _launcher.start_container = None  # type: ignore[attr-defined]
        patched = True

    yield

    if patched:
        delattr(_launcher, "start_container")
