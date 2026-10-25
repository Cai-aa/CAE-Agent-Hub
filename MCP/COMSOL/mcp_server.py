from __future__ import annotations

try:
    from dotenv import load_dotenv
except Exception:  # pragma: no cover
    def load_dotenv(*args: object, **kwargs: object) -> bool:
        return False

from mcp.server.fastmcp import FastMCP

from tools.bridge_client import ComsolBridgeClient
from tools.detect import ROOT, detect_comsol_environment
from tools.mphserver_process import mphserver_status, start_mphserver, stop_mphserver
from tools.mph_session import ComsolMphSessionManager, mph_availability
from tools.model_tools import ComsolModelTools


load_dotenv(ROOT / ".env")

INSTRUCTIONS = """You are controlling COMSOL Multiphysics through MCP.

Prefer the MPh backend for local Windows control: use
comsol_start_session_tool, comsol_session_status_tool, and the
*_session_tool model operations before using the Java bridge / mphserver
fallback. Separate installation detection, session startup, model state, and
solver state. Prefer opening a saved .mph model, changing named parameters,
solving, and exporting tables or plots before attempting broad from-scratch
model construction. Do not claim a license is usable until a MPh session,
bridge command, or COMSOL operation has actually succeeded.

When the user wants to see modeling or solving in COMSOL Desktop, use the
shared-server bridge (tools.shared_bridge), not the independent stand-alone
session. Connect Desktop to that server and import the exact model tag.
Verify a visible model-tree change before claiming Desktop synchronization.
Disconnect shared clients without clearing or removing server models.
"""

mcp = FastMCP("COMSOL MCP", instructions=INSTRUCTIONS)
bridge = ComsolBridgeClient()
models = ComsolModelTools(bridge)
mph_sessions = ComsolMphSessionManager()


@mcp.tool()
def comsol_detect_tool() -> dict:
    """Detect COMSOL executables, Java, API jars, bridge settings, and runs directory."""
    return detect_comsol_environment()


@mcp.tool()
def comsol_mph_availability_tool() -> dict:
    """Check whether the Python MPh package is importable for direct COMSOL sessions."""
    return mph_availability()


@mcp.tool()
def comsol_start_session_tool(
    cores: int | None = 1,
    version: str | None = None,
    standalone: bool | None = True,
    products: list[str] | None = None,
) -> dict:
    """Start a local COMSOL session through MPh. This is the preferred local backend."""
    return mph_sessions.start(cores=cores, version=version, standalone=standalone, products=products)


@mcp.tool()
def comsol_start_session_async_tool(
    cores: int | None = 1,
    version: str | None = None,
    standalone: bool | None = True,
    products: list[str] | None = None,
) -> dict:
    """Start a local COMSOL MPh session in a background job and return immediately."""
    return mph_sessions.start_async(cores=cores, version=version, standalone=standalone, products=products)


@mcp.tool()
def comsol_start_session_status_tool(job_id: str | None = None) -> dict:
    """Return status for the background COMSOL session startup job."""
    return mph_sessions.start_session_status(job_id=job_id)


@mcp.tool()
def comsol_cancel_start_session_tool(job_id: str | None = None) -> dict:
    """Request cancellation of a background COMSOL session startup job."""
    return mph_sessions.cancel_start_session(job_id=job_id)


@mcp.tool()
def comsol_connect_session_tool(port: int, host: str = "localhost") -> dict:
    """Connect MPh to an already-running COMSOL server."""
    return mph_sessions.connect(port=port, host=host)


@mcp.tool()
def comsol_session_status_tool() -> dict:
    """Return status for the MPh-managed COMSOL session."""
    return mph_sessions.status()


@mcp.tool()
def comsol_disconnect_session_tool() -> dict:
    """Disconnect MPh; preserve server models in remote mode (standalone clears locally)."""
    return mph_sessions.disconnect()


@mcp.tool()
def comsol_open_model_session_tool(path: str, set_current: bool = True) -> dict:
    """Open an existing .mph model through the MPh backend."""
    return mph_sessions.open_model(path=path, set_current=set_current)


@mcp.tool()
def comsol_new_model_session_tool(name: str | None = None, set_current: bool = True) -> dict:
    """Create a new COMSOL model through the MPh backend."""
    return mph_sessions.new_model(name=name, set_current=set_current)


@mcp.tool()
def comsol_model_summary_session_tool(model_name: str | None = None) -> dict:
    """Summarize a model loaded in the MPh backend."""
    return {"success": True, "model": mph_sessions.model_summary(model_name)}


@mcp.tool()
def comsol_list_parameters_session_tool(model_name: str | None = None, evaluate: bool = False) -> dict:
    """List parameters for a model loaded in the MPh backend."""
    return mph_sessions.list_parameters(model_name=model_name, evaluate=evaluate)


@mcp.tool()
def comsol_set_parameter_session_tool(
    name: str,
    value: str,
    model_name: str | None = None,
    description: str | None = None,
) -> dict:
    """Set a model parameter through the MPh backend."""
    return mph_sessions.set_parameter(name=name, value=value, model_name=model_name, description=description)


@mcp.tool()
def comsol_solve_session_tool(study: str | None = None, model_name: str | None = None) -> dict:
    """Solve a model through the MPh backend."""
    return mph_sessions.solve(study=study, model_name=model_name)


@mcp.tool()
def comsol_evaluate_session_tool(
    expression: str | list[str],
    unit: str | None = None,
    dataset: str | None = None,
    model_name: str | None = None,
) -> dict:
    """Evaluate a COMSOL expression through the MPh backend."""
    return mph_sessions.evaluate(expression=expression, unit=unit, dataset=dataset, model_name=model_name)


@mcp.tool()
def comsol_export_session_tool(file_path: str, node_name: str | None = None, model_name: str | None = None) -> dict:
    """Run an existing COMSOL export node through the MPh backend."""
    return mph_sessions.export(file_path=file_path, node_name=node_name, model_name=model_name)


@mcp.tool()
def comsol_save_session_tool(
    file_path: str | None = None,
    model_name: str | None = None,
    format: str | None = None,
) -> dict:
    """Save a model through the MPh backend."""
    return mph_sessions.save(file_path=file_path, model_name=model_name, format=format)


@mcp.tool()
def comsol_start_bridge_tool(command: list[str] | str | None = None, cwd: str | None = None) -> dict:
    """Start the configured Java bridge process used for live COMSOL API calls."""
    return bridge.start(command=command, cwd=cwd)


@mcp.tool()
def comsol_bridge_status_tool() -> dict:
    """Return bridge process status for the MCP-owned Java bridge."""
    return bridge.status()


@mcp.tool()
def comsol_stop_bridge_tool() -> dict:
    """Stop the MCP-owned Java bridge process."""
    return bridge.stop()


@mcp.tool()
def comsol_bridge_ping_tool() -> dict:
    """Send a ping request to the live COMSOL bridge."""
    return bridge.request("ping")


@mcp.tool()
def comsol_mphserver_status_tool(host: str = "127.0.0.1", port: int = 2036) -> dict:
    """Check whether a COMSOL mphserver port is listening."""
    return mphserver_status(host=host, port=port)


@mcp.tool()
def comsol_start_mphserver_tool(
    host: str = "127.0.0.1",
    port: int = 2036,
    comsol_exe: str | None = None,
    extra_args: list[str] | None = None,
    wait_seconds: float = 20.0,
) -> dict:
    """Launch COMSOL mphserver through comsol.exe mphserver -port <port>."""
    return start_mphserver(
        host=host,
        port=port,
        comsol_exe=comsol_exe,
        extra_args=extra_args,
        wait_seconds=wait_seconds,
    )


@mcp.tool()
def comsol_stop_mphserver_tool() -> dict:
    """Stop the MCP-owned COMSOL mphserver process, if one was recorded."""
    return stop_mphserver()


@mcp.tool()
def comsol_connect_tool(host: str = "127.0.0.1", port: int = 2036, username: str | None = None, password: str | None = None) -> dict:
    """Connect the Java bridge to a COMSOL mphserver session."""
    return models.connect(host=host, port=port, username=username, password=password)


@mcp.tool()
def comsol_new_model_tool(tag: str = "Model") -> dict:
    """Create a new COMSOL model in the bridge session."""
    return models.new_model(tag=tag)


@mcp.tool()
def comsol_open_model_tool(path: str) -> dict:
    """Open an existing .mph model in the bridge session."""
    return models.open_model(path=path)


@mcp.tool()
def comsol_save_model_tool(path: str | None = None) -> dict:
    """Save the active model, optionally to a new .mph path."""
    return models.save_model(path=path)


@mcp.tool()
def comsol_model_info_tool() -> dict:
    """Return active model metadata, studies, parameters, datasets, plots, and tables."""
    return models.model_info()


@mcp.tool()
def comsol_list_shared_models_tool() -> dict:
    """List model tags on the shared-server bridge without loading a file copy."""
    return bridge.request("listModels")


@mcp.tool()
def comsol_attach_shared_model_tool(model_tag: str) -> dict:
    """Attach to the exact existing server model shown by COMSOL Desktop."""
    return bridge.request("attachModel", {"tag": model_tag})


@mcp.tool()
def comsol_run_shared_script_tool(path: str) -> dict:
    """Run a reviewed local run(context) API script inside the shared script root."""
    return bridge.request("runScript", {"path": path})


@mcp.tool()
def comsol_list_parameters_tool() -> dict:
    """List global parameters from the active COMSOL model."""
    return models.list_parameters()


@mcp.tool()
def comsol_set_parameter_tool(name: str, value: str, description: str | None = None) -> dict:
    """Set a global COMSOL parameter value, for example L='10[mm]'."""
    return models.set_parameter(name=name, value=value, description=description)


@mcp.tool()
def comsol_list_studies_tool() -> dict:
    """List studies from the active COMSOL model."""
    return models.list_studies()


@mcp.tool()
def comsol_run_study_tool(study_tag: str | None = None) -> dict:
    """Run a COMSOL study by tag, or the default study if omitted."""
    return models.run_study(study_tag=study_tag)


@mcp.tool()
def comsol_evaluate_tool(expression: str, dataset: str | None = None, unit: str | None = None) -> dict:
    """Evaluate a COMSOL expression from the active model."""
    return models.evaluate(expression=expression, dataset=dataset, unit=unit)


@mcp.tool()
def comsol_export_plot_tool(plot_group: str, path: str | None = None, width: int = 1600, height: int = 1000) -> dict:
    """Export a plot group from the active model to a PNG file."""
    return models.export_plot(plot_group=plot_group, path=path, width=width, height=height)


@mcp.tool()
def comsol_export_table_tool(table: str, path: str | None = None) -> dict:
    """Export a COMSOL table from the active model to CSV."""
    return models.export_table(table=table, path=path)


@mcp.resource("comsol://agent-instructions")
def agent_instructions() -> str:
    """COMSOL operating guidance for MCP clients."""
    return INSTRUCTIONS


@mcp.resource("comsol://environment")
def comsol_environment() -> dict:
    """Current COMSOL environment detection."""
    return detect_comsol_environment()


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
