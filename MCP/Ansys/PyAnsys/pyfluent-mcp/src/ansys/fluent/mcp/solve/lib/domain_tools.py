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

"""Solve-leaf domain tools (canonical catalog).

A *domain tool* is a stateless backend/catalog operation that has
no dependency on a plan builder, journal, learned constraints, or
recipe registry. (Those belong to the higher-level agent product that
consumes this leaf over MCP, not here.)

Each entry is a typed async function plus a name/description::

    DomainTool(
        spec=DomainToolSpec(name="mesh_quality", description="..."),
        handler=mesh_quality_impl,
    )

The handler signature looks like this::

    async def <name>_impl(
        backend: Backend,
        *,
        arg1: T1,
        arg2: T2 | None = None,
    ) -> dict[str, Any]: ...

:meth:`FluidsLeafMCP._register_one_domain_tool` synthesizes a wrapper
whose ``inspect.Signature`` mirrors the handler minus the leading
``backend`` parameter so that FastMCP can extract the JSON input schema
from the wrapper.

To add a tool, write a typed ``<name>_impl`` coroutine in
``ansys.fluent.mcp.solve.lib.<area>.py`` and append a
:class:`DomainTool` entry to :func:`get_solve_domain_tools`. No
leaf-side changes are needed. ``SolveMCP._register_tools`` already
registers everything this function returns.
"""

from __future__ import annotations

from ansys.fluent.mcp.common.domain_tools import DomainTool, DomainToolSpec
from ansys.fluent.mcp.solve.lib.compare_tools import compare_files_impl
from ansys.fluent.mcp.solve.lib.discovery_tools import list_fields_impl
from ansys.fluent.mcp.solve.lib.mesh_tools import mesh_quality_impl
from ansys.fluent.mcp.solve.lib.schema_probe_tools import (
    describe_named_object_template_impl,
    describe_path_impl,
    get_active_status_impl,
    get_allowed_values_impl,
    probe_path_impl,
)

# NOTE: The engineering reference / correlation tools (lookup_wall_roughness,
# lookup_emissivity, compute_porous_media, compute_htc) encapsulate
# engineering *business logic* and live entirely in the optional
# higher-level agent layer, so the public MCP leaf does not expose them.
# Do NOT add them here.

_MESH_QUALITY_DESCRIPTION = (
    "Return live mesh quality metrics (skewness, orthogonal quality, "
    "aspect-ratio histograms) for the connected Fluent solver. When "
    "``include_check`` is true the response also embeds the output of "
    "Fluent's ``mesh.check()`` command. Use this tool whenever the user "
    "asks 'show mesh quality', 'skewness', 'orthogonal quality', "
    "'aspect ratio', or 'check mesh' — never route those intents "
    "through ``query_reports``."
)

_LIST_FIELDS_DESCRIPTION = (
    "Enumerate the scalar / vector fields available in the loaded "
    "Fluent case (pressure, temperature, velocity-magnitude, "
    "wall-shear, …). Optional ``scope`` filters to cell/node/face "
    "domains (default 'any'). Returns a flat list ready to use in a "
    "report-definition, contour, vector, or one-shot integral. "
    "Requires a live session."
)

_PROBE_PATH_DESCRIPTION = (
    "Batch pre-flight probe for one or more Fluent settings paths. "
    "Returns ``{path: {exists, is_active, is_user_creatable, kind}}`` "
    "in a single round-trip. Use BEFORE writing to a path to verify "
    "(a) the path is a real schema node, (b) it is ACTIVE in the "
    "current solver mode (paths gated by other model toggles return "
    "``is_active=false``), and (c) you may ``.create()`` under a "
    "NamedObject collection (``is_user_creatable``). Inactive paths "
    "are silently ignored by Fluent or raise ``InactiveObjectError`` "
    "at apply — this tool catches both cases up front. Requires a "
    "live session."
)

_GET_ACTIVE_STATUS_DESCRIPTION = (
    "Batch active-status probe for one or more Fluent settings "
    "paths. Returns ``{path: bool}``. Inactive paths cannot be "
    "written — Fluent either silently ignores the write or raises "
    "``InactiveObjectError`` at apply. Use this tool to gate URF / "
    "discretization / model-sub-knob writes whose activity depends "
    "on a sibling model toggle (e.g. ``setup.models.viscous"
    ".k_omega_model`` is inactive unless ``viscous.model='k-omega'``, "
    "``solution.controls.p_v_controls.explicit_*`` is inactive "
    "under SIMPLE / SIMPLEC / PISO). Requires a live session."
)

_GET_ALLOWED_VALUES_DESCRIPTION = (
    "Batch allowed-values probe for one or more Fluent enum / "
    "menu-style settings paths. Returns ``{path: [allowed_values]}``; "
    "paths with no allowed-values constraint return an empty list. "
    "Use BEFORE writing to an enum field (``viscous.model``, "
    "``wall.thermal.thermal_condition``, ``spatial_discretization"
    ".discretization_scheme['mom']``, ...) so the chosen value is "
    "guaranteed to be accepted by Fluent. Requires a live session."
)

_DESCRIBE_NAMED_OBJECT_TEMPLATE_DESCRIPTION = (
    "Describe the field shape of a fresh child under a NamedObject "
    "collection (boundary conditions, cell-zone conditions, report "
    "definitions, materials, surfaces, expressions, ...). Returns "
    "``{child_class, fields, is_active, is_user_creatable, "
    "create_command}`` where ``fields`` carries per-field "
    "``{type_hint, is_active, is_read_only, is_user_creatable, "
    "allowed_values, min, max, default, units}``. Use BEFORE "
    "proposing ``set_named`` / ``multi_edit`` to learn which fields "
    "are required, which are read-only (computed by Fluent), and "
    "which carry an allowed-values constraint. Requires a live "
    "session."
)

_DESCRIBE_PATH_DESCRIPTION = (
    "Batch unified descriptor for one or more Fluent settings paths. "
    "Composes the ``probe_path`` + ``get_allowed_values`` (+ "
    "``describe_named_object_template`` / ``get_command_arguments`` "
    "when the path is a NamedObject collection or a Command) probes "
    "into a single ``PathDescriptor`` per path — one round-trip on "
    "the wire, one shape on the wire, ready to feed the "
    "recipe / validator grounder without stitching four different "
    "envelopes together. Every field defaults to ``null`` (meaning "
    "'unknown / unavailable'); an empty ``allowed_values`` list "
    "carries 'the backend explicitly reports no allowed values', "
    "which is different from ``null`` (probe skipped or failed). "
    "Requires a live session."
)

_COMPARE_FILES_DESCRIPTION = (
    "Open two Fluent case/mesh files in two SEPARATE ephemeral "
    "PyFluent sessions and summarize the differences between them. "
    "Both sessions are launched headless (no_gui) and the cases are "
    "read with lightweight_setup=True for speed; the live workspace "
    "session, if any, is NOT touched. Returns a structured diff of "
    "global model state and per-family named-object name lists. Use "
    "for questions like 'what changed between these two cases?', "
    "'compare A.cas.h5 and B.cas.h5'. The response includes a "
    "pre-rendered markdown table in the 'summary' field grouped by "
    "hierarchy. Reply with that 'summary' string verbatim — its "
    "column headers ARE the actual file names and a '—' cell means "
    "'not present in that file'. Do NOT re-label files as 'File A' / "
    "'File B', do NOT add a 'Change' column back, and do NOT "
    "paraphrase the table into bullet lists."
)


def get_solve_domain_tools() -> list[DomainTool]:
    """Return the canonical solve-leaf domain-tool catalog.

    The :meth:`FluidsLeafMCP._register_domain_tools` helper consumes
    this list and binds each entry to ``self.tool`` with a
    signature-preserving wrapper.

    Returns
    -------
    list[DomainTool]
        Collection containing the operation results.
    """
    return [
        DomainTool(
            spec=DomainToolSpec(
                name="mesh_quality",
                description=_MESH_QUALITY_DESCRIPTION,
            ),
            handler=mesh_quality_impl,
        ),
        DomainTool(
            spec=DomainToolSpec(
                name="list_fields",
                description=_LIST_FIELDS_DESCRIPTION,
            ),
            handler=list_fields_impl,
        ),
        DomainTool(
            spec=DomainToolSpec(
                name="compare_files",
                description=_COMPARE_FILES_DESCRIPTION,
            ),
            handler=compare_files_impl,
        ),
        DomainTool(
            spec=DomainToolSpec(
                name="probe_path",
                description=_PROBE_PATH_DESCRIPTION,
            ),
            handler=probe_path_impl,
        ),
        DomainTool(
            spec=DomainToolSpec(
                name="get_active_status",
                description=_GET_ACTIVE_STATUS_DESCRIPTION,
            ),
            handler=get_active_status_impl,
        ),
        DomainTool(
            spec=DomainToolSpec(
                name="get_allowed_values",
                description=_GET_ALLOWED_VALUES_DESCRIPTION,
            ),
            handler=get_allowed_values_impl,
        ),
        DomainTool(
            spec=DomainToolSpec(
                name="describe_named_object_template",
                description=_DESCRIBE_NAMED_OBJECT_TEMPLATE_DESCRIPTION,
            ),
            handler=describe_named_object_template_impl,
        ),
        DomainTool(
            spec=DomainToolSpec(
                name="describe_path",
                description=_DESCRIBE_PATH_DESCRIPTION,
            ),
            handler=describe_path_impl,
        ),
    ]


__all__ = ["get_solve_domain_tools"]
