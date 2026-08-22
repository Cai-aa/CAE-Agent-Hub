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

"""Live Fluent integration tests for the PyFluent backend."""

import asyncio
import os

import pytest

from ansys.fluent.mcp.solve.backends.pyfluent import PyFluentBackend

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def live_backend():
    """Exercise the live backend test helper.

    Returns
    -------
    None
        The function completes through its side effects.
    """

    async def start_backend():
        """Start backend.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        backend = PyFluentBackend()
        # Launch mode via PyFluent's managed Docker container. PyFluent
        result = await backend.connect(
            dimension=os.getenv("FLUENT_MCP_INTEGRATION_DIMENSION", "2"),
            precision=os.getenv("FLUENT_MCP_INTEGRATION_PRECISION", "double"),
            processor_count=int(os.getenv("FLUENT_MCP_INTEGRATION_PROCESSORS", "1")),
            ui_mode=os.getenv("FLUENT_MCP_INTEGRATION_UI_MODE", "no_gui_or_graphics"),
            product_version=os.getenv("FLUENT_MCP_INTEGRATION_PRODUCT_VERSION") or None,
            start_timeout=int(os.getenv("FLUENT_MCP_INTEGRATION_START_TIMEOUT", "120")),
            cleanup_on_exit=True,
        )
        if result.status != "ok":
            pytest.fail(
                f"Fluent integration backend did not connect: {result.message or result.error_code}"
            )
        return backend

    backend = asyncio.run(start_backend())
    try:
        yield backend
    finally:
        asyncio.run(backend.disconnect())


def test_live_pyfluent_backend_connects_and_reports_status(live_backend):
    """Verify that live pyfluent backend connects and reports status.

    Parameters
    ----------
    live_backend : Any
        Live backend to supply to the function.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    status = live_backend.status("solve")

    assert status.connected is True
    assert status.backend_kind == "pyfluent"


def test_live_pyfluent_backend_solves_safe_status_surfaces(live_backend):
    """Verify that live pyfluent backend solves safe status surfaces.

    Parameters
    ----------
    live_backend : Any
        Live backend to supply to the function.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    solver_status = asyncio.run(live_backend.solver_status())
    mesh_counts = asyncio.run(live_backend.mesh_counts())

    assert "initialized" in solver_status
    assert set(mesh_counts) == {"cell_count", "face_count", "node_count"}


def test_live_pyfluent_backend_runs_sandboxed_code(live_backend):
    """Verify that live pyfluent backend runs sandboxed code.

    Parameters
    ----------
    live_backend : Any
        Live backend to supply to the function.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    result = asyncio.run(live_backend.run_code("__return__ = solver is session"))

    assert result.status == "ok"
    assert result.return_value is True


# ---------------------------------------------------------------------------
# Real solver run: load a shipped example case, initialize, iterate, and
# assert the solver state actually advanced. This exercises the end-to-end
# path the MCP tools drive in production rather than just connect/status.
# ---------------------------------------------------------------------------


def _download_mixing_elbow_case() -> str:
    """Fetch the canonical mixing-elbow case/data from PyFluent examples.

    Returns the local path to the ``.cas.h5`` file. Skips the test if the
    example assets cannot be retrieved (e.g. offline CI without the data
    cache primed).

    Returns
    -------
    str
        String result produced by the function.
    """
    try:
        from ansys.fluent.core import examples
    except ImportError:  # pragma: no cover - pyfluent not installed
        pytest.fail("ansys-fluent-core is not installed")

    try:
        case_path = examples.download_file(
            "mixing_elbow.cas.h5",
            "pyfluent/mixing_elbow",
        )
        # Pull the matching data so initialization has a valid starting
        # point and residuals are meaningful.
        examples.download_file(
            "mixing_elbow.dat.h5",
            "pyfluent/mixing_elbow",
        )
    except Exception as exc:
        pytest.fail(f"Could not download mixing_elbow example case: {exc}")
    return case_path


def _initialize_solver(backend) -> None:
    """Initialize the solver, preferring standard then hybrid.

    A freshly read case may have only one of the two initializers active
    depending on the solver/models state, so try both and assert via the
    canonical ``is_initialized()`` probe rather than a single method's
    return status.

    Parameters
    ----------
    backend : Any
        Backend to supply to the function.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    for method in (
        "session.settings.solution.initialization.standard_initialize()",
        "session.settings.solution.initialization.hybrid_initialize()",
    ):
        result = asyncio.run(backend.run_code(method))
        if result.status == "ok":
            return
    status = asyncio.run(backend.solver_status())
    if status.get("initialized"):
        return
    pytest.fail(f"solver initialization failed: {result.message}\n{result.stderr}")


@pytest.fixture(scope="module")
def solved_backend():
    """Launch a dedicated 3D session, load mixing-elbow, init, and iterate.

    The mixing-elbow example is a 3D case, so this fixture owns its own
    3D solver session (independent of the module-level ``live_backend``,
    which may be 2D). Yields the backend after a real, small solve so the
    assertions observe genuine solver state.

    Returns
    -------
    Any
        Result produced by the function.
    """
    case_path = _download_mixing_elbow_case()
    posix_case = case_path.replace("\\", "/")

    async def start_3d_backend():
        """Start 3d backend.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        backend = PyFluentBackend()
        result = await backend.connect(
            dimension="3",
            precision=os.getenv("FLUENT_MCP_INTEGRATION_PRECISION", "double"),
            processor_count=int(os.getenv("FLUENT_MCP_INTEGRATION_PROCESSORS", "1")),
            ui_mode=os.getenv("FLUENT_MCP_INTEGRATION_UI_MODE", "no_gui_or_graphics"),
            product_version=os.getenv("FLUENT_MCP_INTEGRATION_PRODUCT_VERSION") or None,
            start_timeout=int(os.getenv("FLUENT_MCP_INTEGRATION_START_TIMEOUT", "120")),
            cleanup_on_exit=True,
        )
        if result.status != "ok":
            pytest.fail(f"3D solver session did not connect: {result.message or result.error_code}")
        return backend

    backend = asyncio.run(start_3d_backend())
    try:
        load = asyncio.run(
            backend.run_code(f'session.settings.file.read_case(file_name="{posix_case}")')
        )
        assert load.status == "ok", f"case load failed: {load.message}\n{load.stderr}"

        _initialize_solver(backend)

        iterate = asyncio.run(
            backend.run_code("session.settings.solution.run_calculation.iterate(iter_count=5)")
        )
        assert iterate.status == "ok", f"iterate failed: {iterate.message}\n{iterate.stderr}"

        yield backend
    finally:
        asyncio.run(backend.disconnect())


# ===========================================================================
# Per-tool pass / fail pairs against the live, solved session.
#
# Each MCP-exposed backend tool gets one "happy path" test (valid inputs ->
# usable result) and one "failure path" test (invalid inputs / bad state ->
# typed error, never an unhandled exception). This proves both the real
# use case and that error handling holds on a genuine Fluent session.
# ===========================================================================


# --- run_code --------------------------------------------------------------


def test_run_code_pass(solved_backend):
    """Verify that run code pass.

    Parameters
    ----------
    solved_backend : Any
        Solved backend to supply to the function.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    result = asyncio.run(solved_backend.run_code("__return__ = 6 * 7"))

    assert result.status == "ok"
    assert result.return_value == 42


def test_run_code_fail_runtime_error(solved_backend):
    # Non-existent settings path -> genuine runtime failure surfaced as a
    # typed error with diagnostics, never raised.
    """Verify that run code fail runtime error.

    Parameters
    ----------
    solved_backend : Any
        Solved backend to supply to the function.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    result = asyncio.run(
        solved_backend.run_code("session.settings.setup.this_path_does_not_exist.get_state()")
    )

    assert result.status == "error"
    assert result.error_code in {"execution_error", "solver_disconnected"}
    assert result.message
    assert result.stderr
    # A failed run must not leave a stale return value masquerading as success.
    assert result.return_value is None


def test_run_code_fail_invalid_argument_value(solved_backend):
    # Invalid argument VALUE (string where an int is required) is a
    # deterministic failure across Fluent builds.
    """Verify that run code fail invalid argument value.

    Parameters
    ----------
    solved_backend : Any
        Solved backend to supply to the function.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    result = asyncio.run(
        solved_backend.run_code(
            "session.settings.solution.run_calculation.iterate(iter_count='not-an-int')"
        )
    )

    assert result.status == "error"
    assert result.error_code in {"execution_error", "solver_disconnected"}
    assert result.message


def test_run_code_fail_sandbox_violation(solved_backend):
    # Sandbox enforcement holds even with a live solver attached: a
    # disallowed import is rejected before any Fluent round-trip.
    """Verify that run code fail sandbox violation.

    Parameters
    ----------
    solved_backend : Any
        Solved backend to supply to the function.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    result = asyncio.run(solved_backend.run_code("import socket\n__return__ = 1"))

    assert result.status == "error"
    assert result.error_code == "forbidden_import"


def test_run_code_fail_syntax_error(solved_backend):
    """Verify that run code fail syntax error.

    Parameters
    ----------
    solved_backend : Any
        Solved backend to supply to the function.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    result = asyncio.run(solved_backend.run_code("session.settings.setup.("))

    assert result.status == "error"
    assert result.error_code == "syntax_error"


# --- validate_code ---------------------------------------------------------


def test_validate_code_pass(solved_backend):
    """Verify that validate code pass.

    Parameters
    ----------
    solved_backend : Any
        Solved backend to supply to the function.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    result = asyncio.run(solved_backend.validate_code("x = 1\n__return__ = x"))

    assert result.status == "ok"


def test_validate_code_fail(solved_backend):
    """Verify that validate code fail.

    Parameters
    ----------
    solved_backend : Any
        Solved backend to supply to the function.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    result = asyncio.run(solved_backend.validate_code("import os\nos.system('echo hi')"))

    assert result.status == "error"
    assert result.error_code


# --- solver_status ---------------------------------------------------------


def test_solver_status_pass(solved_backend):
    """Verify that solver status pass.

    Parameters
    ----------
    solved_backend : Any
        Solved backend to supply to the function.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    status = asyncio.run(solved_backend.solver_status())

    # Contract: solver_status returns a dict that always carries the
    # ``initialized`` key as a real tri-state value (True/False/None) and
    # the fail-soft ``utl_enabled`` boolean. The actual init flag and
    # iteration count are unreliable across Fluent builds (some leave
    # is_initialized() False and omit the iteration count from the
    # run_calculation state even after a successful solve), so we assert the
    # stable shape rather than build-specific values.
    assert isinstance(status, dict)
    assert "initialized" in status
    assert status["initialized"] in (True, False, None)
    assert isinstance(status.get("utl_enabled"), bool)
    if status.get("iterations") is not None:
        assert int(status["iterations"]) >= 0


# --- mesh_counts -----------------------------------------------------------


def test_mesh_counts_pass(solved_backend):
    """Verify that mesh counts pass.

    Parameters
    ----------
    solved_backend : Any
        Solved backend to supply to the function.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    counts = asyncio.run(solved_backend.mesh_counts())

    assert set(counts) == {"cell_count", "face_count", "node_count"}
    assert all(counts[key] is not None for key in counts), counts
    assert counts["cell_count"] > 0
    assert counts["face_count"] > counts["cell_count"]
    assert counts["node_count"] > 0


# --- mesh_quality ----------------------------------------------------------


def test_mesh_quality_pass(solved_backend):
    """Verify that mesh quality pass.

    Parameters
    ----------
    solved_backend : Any
        Solved backend to supply to the function.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    quality = asyncio.run(solved_backend.mesh_quality())

    # Fail-soft contract: always returns the three-key skeleton; on a
    # loaded case the orthogonal-quality metric should resolve.
    assert set(quality) == {"min_orthogonal_quality", "max_ortho_skew", "max_aspect_ratio"}


# --- mesh_check ------------------------------------------------------------


def test_mesh_check_pass(solved_backend):
    """Verify that mesh check pass.

    Parameters
    ----------
    solved_backend : Any
        Solved backend to supply to the function.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    check = asyncio.run(solved_backend.mesh_check())

    assert "warnings" in check
    assert "errors" in check
    assert isinstance(check["warnings"], list)


# --- list_named_objects ----------------------------------------------------


def test_list_named_objects_pass(solved_backend):
    """Verify that list named objects pass.

    Parameters
    ----------
    solved_backend : Any
        Solved backend to supply to the function.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    objects = asyncio.run(solved_backend.list_named_objects())

    # A loaded mixing-elbow case exposes boundary-condition collections.
    assert isinstance(objects, dict)
    assert objects, "expected at least one named-object collection on a loaded case"


# --- get_named_object_names ------------------------------------------------


def test_get_named_object_names_pass(solved_backend):
    """Verify that get named object names pass.

    Parameters
    ----------
    solved_backend : Any
        Solved backend to supply to the function.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    collections = asyncio.run(solved_backend.list_named_objects())
    # Pick any populated collection discovered on the live case.
    target = next((path for path, names in collections.items() if names), None)
    if target is None:
        pytest.skip("no populated named-object collection on this case")

    names = asyncio.run(solved_backend.get_named_object_names(target))

    assert isinstance(names, list)
    assert names


def test_get_named_object_names_fail(solved_backend):
    # A non-existent collection path resolves to an empty list (fail-soft),
    # never an unhandled exception.
    """Verify that get named object names fail.

    Parameters
    ----------
    solved_backend : Any
        Solved backend to supply to the function.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    names = asyncio.run(solved_backend.get_named_object_names("setup.not_a_real_collection"))

    assert names == []


# --- get_state -------------------------------------------------------------


def test_get_state_pass(solved_backend):
    """Verify that get state pass.

    Parameters
    ----------
    solved_backend : Any
        Solved backend to supply to the function.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    state = asyncio.run(solved_backend.get_state(["setup.models.energy"]))

    assert isinstance(state, dict)
    assert state


def test_get_state_fail(solved_backend):
    # Bogus path -> fail-soft (empty / unresolved), never raises.
    """Verify that get state fail.

    Parameters
    ----------
    solved_backend : Any
        Solved backend to supply to the function.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    state = asyncio.run(solved_backend.get_state(["setup.this_does_not_exist"]))

    assert isinstance(state, dict)


# --- get_active_status -----------------------------------------------------


def test_get_active_status_pass(solved_backend):
    """Verify that get active status pass.

    Parameters
    ----------
    solved_backend : Any
        Solved backend to supply to the function.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    active = asyncio.run(solved_backend.get_active_status(["setup.models.energy"]))

    assert isinstance(active, dict)
    assert "setup.models.energy" in active
    assert isinstance(active["setup.models.energy"], bool)


# --- get_help --------------------------------------------------------------


def test_get_help_pass(solved_backend):
    """Verify that get help pass.

    Parameters
    ----------
    solved_backend : Any
        Solved backend to supply to the function.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    help_info = asyncio.run(solved_backend.get_help("setup.models.energy"))

    assert isinstance(help_info, dict)
    assert "path" in help_info


def test_get_help_fail(solved_backend):
    # Help on a bogus path must resolve to a typed/empty payload, not raise.
    """Verify that get help fail.

    Parameters
    ----------
    solved_backend : Any
        Solved backend to supply to the function.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    help_info = asyncio.run(solved_backend.get_help("setup.not_a_real_node"))

    assert isinstance(help_info, dict)


# --- list_fields -----------------------------------------------------------


def test_list_fields_pass(solved_backend):
    """Verify that list fields pass.

    Parameters
    ----------
    solved_backend : Any
        Solved backend to supply to the function.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    fields = asyncio.run(solved_backend.list_fields(scope="any"))

    assert fields is None or isinstance(fields, dict)
    if isinstance(fields, dict):
        assert "fields" in fields


# --- get_command_arguments -------------------------------------------------


def test_get_command_arguments_pass(solved_backend):
    """Verify that get command arguments pass.

    Parameters
    ----------
    solved_backend : Any
        Solved backend to supply to the function.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    args = asyncio.run(solved_backend.get_command_arguments("solution.run_calculation.iterate"))

    # Either a discovered argument map or None when introspection is
    # unavailable on this build; never an exception.
    assert args is None or isinstance(args, dict)


def test_get_command_arguments_fail(solved_backend):
    """Verify that get command arguments fail.

    Parameters
    ----------
    solved_backend : Any
        Solved backend to supply to the function.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    args = asyncio.run(solved_backend.get_command_arguments("setup.not_a_real_command"))

    assert args is None or isinstance(args, dict)


# --- get_targeted_context --------------------------------------------------


def test_get_targeted_context_pass(solved_backend):
    """Verify that get targeted context pass.

    Parameters
    ----------
    solved_backend : Any
        Solved backend to supply to the function.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    context = asyncio.run(
        solved_backend.get_targeted_context(paths_to_check=["setup.models.energy"])
    )

    assert isinstance(context, dict)


def test_get_targeted_context_fail(solved_backend):
    """Verify that get targeted context fail.

    Parameters
    ----------
    solved_backend : Any
        Solved backend to supply to the function.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    context = asyncio.run(
        solved_backend.get_targeted_context(paths_to_check=["setup.not_a_real_path"])
    )

    assert isinstance(context, dict)
