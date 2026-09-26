from __future__ import annotations

import os

from fastmcp import FastMCP

from .bridge_client import LiveBridgeClient
from .cantilever_demo import (
    export_visible_cantilever,
    import_visible_cantilever,
    inspect_visible_cantilever,
    inspect_cantilever,
    prepare_cantilever,
    solve_visible_cantilever,
    solve_cantilever,
    stage_visible_cantilever,
)
from .environment import environment_report
from .settings import Settings, safe_relative_path, within


INSTRUCTIONS = """Control a live BETA CAE Systems ANSA session through MCP tools.
Call get_environment and get_live_bridge_status before relying on live state. Read tools
query the current ANSA database through a mutually authenticated localhost bridge. Model
checks report actual ANSA Check results. Creating entities, changing card values, saving
the database, and refreshing the view are side effects and require explicit confirmation.
Before changing the model, read the current session nonce, database, and entity and use
those expected values to prevent stale writes. Save only beneath the configured MCP workspace.
The execute_live_ansa_python_step tool intentionally executes unrestricted Python in the
current ANSA GUI process. It is NOT sandboxed and can access local files/processes with
ANSA's privileges. Review code and current model before each confirmed call. Split a
workflow into small calls: every mutation call returns a live-step record and asks ANSA
to redraw before returning to its GUI event loop. Long single calls do not show every
internal operation. A successful redraw API return is not visual or engineering proof.
A reachable bridge proves connectivity, not mesh quality or engineering validity.
Use get_live_capabilities for named operation parameters and availability. Use
search_live_ansa_api and get_live_ansa_api_help to consult the connected version's
API before writing Python. Missing capabilities must fail closed; API presence
does not establish signature compatibility. General mesh operations use ANSA's
current mesh settings; inspect and agree these first, then run checks afterward.
External solver execution and engineering certification are not generic ANSA operations.
Example tools are disabled unless ANSA_MCP_ENABLE_EXAMPLES=1 is explicitly set.
"""

settings = Settings.from_env()
settings.ensure()
live = LiveBridgeClient()
mcp = FastMCP(
    "ansa",
    instructions=INSTRUCTIONS,
    strict_input_validation=True,
)


@mcp.tool()
def get_environment() -> dict:
    """Detect the ANSA installation, local docs, workspace, and live bridge."""
    report = environment_report(settings)
    bridge = live.status(connect_timeout=0.25)
    report["capabilities"]["live_authenticated_bridge"] = bridge["connected"]
    report["live_bridge"] = bridge
    return report


@mcp.tool()
def get_live_bridge_status() -> dict:
    """Probe the authenticated bridge inside the currently running ANSA GUI."""
    return live.status(connect_timeout=0.75)


@mcp.tool()
def get_live_capabilities() -> dict:
    """Return the exact allowlisted operations supported by the loaded ANSA bridge."""
    return live.call("get_capabilities")


@mcp.tool()
def get_live_session_info() -> dict:
    """Return ANSA version/runtime, current deck, and current database path."""
    return live.call("get_session_info")


@mcp.tool()
def get_live_model_summary(
    entity_types: list[str] | None = None,
    visible_only: bool = False,
) -> dict:
    """Count selected entity types in the current ANSA database."""
    return live.call(
        "get_model_summary",
        {"entity_types": entity_types, "visible_only": visible_only},
    )


@mcp.tool()
def list_live_entities(
    entity_type: str,
    fields: list[str] | None = None,
    limit: int = 100,
    offset: int = 0,
    visible_only: bool = False,
) -> dict:
    """List a bounded page of live entities and selected card fields."""
    return live.call(
        "list_entities",
        {
            "entity_type": entity_type,
            "fields": fields,
            "limit": limit,
            "offset": offset,
            "visible_only": visible_only,
        },
    )


@mcp.tool()
def get_live_entity(
    entity_type: str,
    entity_id: int,
    fields: list[str] | None = None,
) -> dict:
    """Read one current-deck entity by exact ANSA type and ID."""
    return live.call(
        "get_entity",
        {"entity_type": entity_type, "entity_id": entity_id, "fields": fields},
    )


@mcp.tool()
def run_live_model_checks(
    check_names: list[str] | None = None,
    max_issues: int = 200,
) -> dict:
    """Run allowlisted ANSA checks without opening the Checks Results UI."""
    return live.call(
        "run_model_checks",
        {"check_names": check_names, "max_issues": max_issues},
    )


@mcp.tool()
def save_live_database(
    relative_path: str,
    expected_database: str,
    expected_session_nonce: str,
    operation_id: str,
    confirm: bool = False,
    overwrite: bool = False,
) -> dict:
    """Write a verified workspace-scoped .ansa snapshot without renaming the live database."""
    relative = safe_relative_path(relative_path, suffix=".ansa")
    target = within(settings.workspace / relative, settings.workspace)
    return live.call_persistent_write(
        "save_database",
        {
            "path": str(target),
            "expected_database": expected_database,
            "expected_session_nonce": expected_session_nonce,
            "operation_id": operation_id,
            "confirm": confirm,
            "overwrite": overwrite,
        },
        operation_id=operation_id,
    )


@mcp.tool()
def create_live_entity(
    entity_type: str,
    fields: dict,
    expected_database: str,
    expected_session_nonce: str,
    operation_id: str,
    confirm: bool = False,
) -> dict:
    """Create one typed entity after session and database identity confirmation."""
    return live.call_persistent_write(
        "create_entity",
        {
            "entity_type": entity_type,
            "fields": fields,
            "expected_database": expected_database,
            "expected_session_nonce": expected_session_nonce,
            "operation_id": operation_id,
            "confirm": confirm,
        },
        operation_id=operation_id,
    )


@mcp.tool()
def set_live_entity_card_values(
    entity_type: str,
    entity_id: int,
    values: dict,
    expected_values: dict,
    expected_database: str,
    expected_session_nonce: str,
    operation_id: str,
    confirm: bool = False,
) -> dict:
    """CAS-update fields after matching expected session, database, and values."""
    return live.call_persistent_write(
        "set_entity_card_values",
        {
            "entity_type": entity_type,
            "entity_id": entity_id,
            "values": values,
            "expected_values": expected_values,
            "expected_database": expected_database,
            "expected_session_nonce": expected_session_nonce,
            "operation_id": operation_id,
            "confirm": confirm,
        },
        operation_id=operation_id,
    )


@mcp.tool()
def refresh_live_view(confirm: bool = False) -> dict:
    """Redraw the current ANSA model view."""
    return live.call("refresh_view", {"confirm": confirm})


@mcp.tool()
def get_live_step_history(limit: int = 20) -> dict:
    """Read recent model-changing MCP steps from this ANSA GUI bridge session."""
    return live.call("get_step_history", {"limit": limit})


@mcp.tool()
def execute_live_ansa_python_step(
    step_name: str,
    code: str,
    expected_database: str,
    expected_session_nonce: str,
    expected_deck: int,
    operation_id: str,
    confirm: bool = False,
) -> dict:
    """Run one unrestricted Python step inside ANSA GUI, then redraw and record it.

    DANGEROUS: this is not a sandbox. Python has ANSA's local filesystem and
    process privileges. Use small, reviewable steps and a fresh operation_id;
    read model state before and after. A long script's internal operations are
    not individually visible. If outcome is unknown, do not use a new ID to retry.
    """
    return live.call_persistent_write(
        "execute_python_step",
        {
            "step_name": step_name,
            "code": code,
            "expected_database": expected_database,
            "expected_session_nonce": expected_session_nonce,
            "expected_deck": expected_deck,
            "operation_id": operation_id,
            "confirm": confirm,
        },
        operation_id=operation_id,
    )


def example_tool():
    """Legacy teaching examples are not registered by default."""
    return mcp.tool() if os.environ.get("ANSA_MCP_ENABLE_EXAMPLES") == "1" else lambda fn: fn


@mcp.tool()
def search_live_ansa_api(module: str, query: str = "", offset: int = 0, limit: int = 50) -> dict:
    """Search public symbols in the connected ANSA version; does not execute them."""
    return live.call("search_api", {"module": module, "query": query, "offset": offset, "limit": limit})


@mcp.tool()
def get_live_ansa_api_help(module: str, name: str) -> dict:
    """Read runtime signature/docstring for one public API, without invoking it."""
    return live.call("get_api_help", {"module": module, "name": name})


@mcp.tool()
def get_live_entity_fields(entity_type: str, entity_id: int) -> dict:
    """Discover valid card field names for an existing entity in the current deck."""
    return live.call("get_entity_fields", {"entity_type": entity_type, "entity_id": entity_id})


@mcp.tool()
def execute_live_ansa_operation(operation: str, parameters: dict, expected_database: str,
                                expected_session_nonce: str, expected_deck: int,
                                operation_id: str, confirm: bool = False) -> dict:
    """Execute one guarded generic operation and redraw the live ANSA window.

    First read get_live_capabilities.general_operations.operations for exact
    parameter keys and availability. Covers Open, deck switch, hide/isolate,
    deletion, curves, selected geometry checks/fixes, surface/volume meshing,
    quality repair, materials, entity references, Abaqus loads/constraints/contact,
    and guarded flat Abaqus/Nastran import/export. Solver-specific restrictions
    are documented in the capability parameter contracts. No hidden fallback.
    Save before destructive actions; an uncertain result must not be retried
    with a new operation ID. No automatic rollback or solver validation.
    """
    return live.call_persistent_write("execute_operation", {
        "operation": operation, "parameters": parameters,
        "expected_database": expected_database, "expected_session_nonce": expected_session_nonce,
        "expected_deck": expected_deck, "operation_id": operation_id, "confirm": confirm,
    }, operation_id=operation_id)


@example_tool()
def prepare_cantilever_static_demo(confirm: bool = False) -> dict:
    """Build a fixed 200 x 20 x 10 mm solid cantilever in ANSA batch mode.

    ANSA imports a deterministic mesh, checks entity counts, saves its .ansa
    database, and exports an Abaqus/Standard deck into a new workspace folder.
    The currently open GUI database is not modified.
    """
    if confirm is not True:
        raise ValueError("Explicit confirm=true is required to create the demo")
    return prepare_cantilever(settings)


@example_tool()
def solve_cantilever_static_demo(run_id: str, confirm: bool = False) -> dict:
    """Run installed Abaqus/Standard on the ANSA-exported demo deck."""
    if confirm is not True:
        raise ValueError("Explicit confirm=true is required to start the solver")
    return solve_cantilever(settings, run_id)


@example_tool()
def inspect_cantilever_static_demo(run_id: str) -> dict:
    """Read Abaqus ODB displacements, stress, and reaction balance."""
    return inspect_cantilever(settings, run_id)


@example_tool()
def stage_visible_cantilever_static_demo(confirm: bool = False) -> dict:
    """Stage the fixed cantilever source for the open ANSA GUI workflow."""
    if confirm is not True:
        raise ValueError("Explicit confirm=true is required to stage the demo")
    return stage_visible_cantilever(settings, live)


@example_tool()
def import_visible_cantilever_static_demo(
    run_id: str,
    expected_database: str,
    expected_session_nonce: str,
    operation_id: str,
    confirm: bool = False,
) -> dict:
    """Import the fixed mesh into a new empty ANSA GUI model and redraw it."""
    if confirm is not True:
        raise ValueError("Explicit confirm=true is required to import the live demo")
    return import_visible_cantilever(
        settings, live, run_id, expected_database, expected_session_nonce, operation_id
    )


@example_tool()
def export_visible_cantilever_static_demo(
    run_id: str,
    expected_database: str,
    expected_session_nonce: str,
    operation_id: str,
    confirm: bool = False,
) -> dict:
    """Save and export the model currently visible in ANSA for Abaqus solving."""
    if confirm is not True:
        raise ValueError("Explicit confirm=true is required to export the live demo")
    return export_visible_cantilever(
        settings, live, run_id, expected_database, expected_session_nonce, operation_id
    )


@example_tool()
def solve_visible_cantilever_static_demo(run_id: str, confirm: bool = False) -> dict:
    """Keep the ANSA model visible while Abaqus/Standard solves its export."""
    if confirm is not True:
        raise ValueError("Explicit confirm=true is required to start the solver")
    return solve_visible_cantilever(settings, live, run_id)


@example_tool()
def inspect_visible_cantilever_static_demo(run_id: str) -> dict:
    """Read the visible workflow's Abaqus ODB and verify its static results."""
    return inspect_visible_cantilever(settings, live, run_id)


@mcp.resource("ansa://environment")
def environment_resource() -> str:
    """Machine-readable installation and bridge status."""
    import json

    return json.dumps(get_environment(), ensure_ascii=False, indent=2)
