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

from ansys.fluent.mcp.solve.lib import intent_guard


def _signatures(code, **kwargs):
    """Return representative intent-guard signatures for tests.

    Parameters
    ----------
    code : Any
        Python code or command text to execute or validate.
    kwargs : Any
        Keyword arguments forwarded to the callable.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    return {finding.signature for finding in intent_guard.evaluate(code, **kwargs).findings}


def test_enable_flag_defaults_on_and_accepts_falsy_values():
    """Verify that enable flag defaults on and accepts falsy values.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    assert intent_guard.is_enabled({}) is True
    assert intent_guard.is_enabled({"FLUIDS_MCP_INTENT_GUARD": "1"}) is True
    assert intent_guard.is_enabled({"FLUIDS_MCP_INTENT_GUARD": " off "}) is False


def test_boundary_rename_and_multiphase_blocks_render_result():
    """Verify that boundary rename and multiphase blocks render result.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    code = """
solver.settings.setup.boundary_conditions.velocity_inlet["inlet-1"].name = "oil inlet"
solver.settings.setup.models.multiphase.number_of_phases = 3
"""
    report = intent_guard.evaluate(code)
    result = report.to_run_code_result()

    assert report.has_blocking is True
    assert "bc.rename.whitespace" in _signatures(code)
    assert "multiphase.number_of_phases.shape" in _signatures(code)
    assert result.status == "error"
    assert result.error_code == "risk_blocked"
    assert "Use an underscored name" in result.stderr
    assert "number_of_eulerian_phases" in result.stderr


def test_rename_call_with_whitespace_is_blocked():
    """Verify that rename call with whitespace is blocked.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    report = intent_guard.evaluate(
        'solver.settings.setup.boundary_conditions.wall.rename("new wall", "old_wall")'
    )

    assert report.findings[0].signature == "bc.rename.whitespace"
    assert report.findings[0].line == 1


def test_sequence_findings_use_sequence_error():
    """Verify that sequence findings use sequence error.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    report = intent_guard.evaluate(
        """
solver.settings.setup.models.multiphase.phases["phase-1"].material = "water"
solver.settings.setup.models.multiphase.phases["phase-1"].name = "water-phase"
"""
    )
    result = report.to_run_code_result()

    assert result.error_code == "sequence_error"
    assert "seq.phase.material_before_rename" in result.stderr


def test_write_while_iterating_blocks_setup_mutation():
    """Verify that write while iterating blocks setup mutation.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    report = intent_guard.evaluate(
        "solver.settings.setup.models.energy.enabled = True",
        iterating=True,
    )

    assert report.findings[0].signature == "runtime.write_during_iter"


def test_named_expression_forward_reference_block_warn_and_live_skip():
    """Verify that named expression forward reference block warn and live skip.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    create_after_use = """
solver.settings.setup.boundary_conditions.velocity_inlet["inlet"].momentum.x_component = "expr_grav"
solver.settings.setup.named_expressions["expr_grav"] = {"definition": "9.81 [m s^-2]"}
"""
    missing = 'solver.settings.setup.boundary_conditions.velocity_inlet["inlet"].momentum.x_component = "expr_grav"'  # noqa: E501
    live = {"setup.named_expressions": ["expr_grav"]}

    assert "seq.named_expr.use_before_create" in _signatures(create_after_use)
    missing_report = intent_guard.evaluate(missing)
    assert missing_report.findings[0].signature == "named_expr.unknown"
    assert missing_report.findings[0].severity == "warn"
    assert intent_guard.evaluate(missing, live_named_objects=live).findings == []


def test_report_definition_surface_shapes_are_blocked():
    """Verify that report definition surface shapes are blocked.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    attr_report = intent_guard.evaluate(
        'solver.settings.solution.report_definitions.surface["r1"].surfaces = ["wall"]'
    )
    dict_report = intent_guard.evaluate(
        'solver.settings.solution.report_definitions.surface["r1"] = {"locations": ["wall"]}'
    )

    assert attr_report.findings[0].signature == "reportdef.surface_field"
    assert dict_report.findings[0].signature == "reportdef.surface_field"


def test_named_expression_units_and_tui_warn_once():
    """Verify that named expression units and tui warn once.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    report = intent_guard.evaluate(
        """
solver.settings.setup.named_expressions["g"] = {"definition": "9.81"}
solver.tui.file.read_case("case.cas.h5")
solver.tui.mesh.check()
"""
    )

    signatures = [finding.signature for finding in report.findings]
    assert signatures.count("named_expr.missing_units") == 1
    assert signatures.count("tui.usage") == 1
    assert report.has_blocking is False
    assert report.to_run_code_result().error_code == "risk_blocked"


def test_empty_or_invalid_code_has_no_findings():
    """Verify that empty or invalid code has no findings.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    assert intent_guard.evaluate("").findings == []
    assert intent_guard.evaluate("if broken").findings == []
