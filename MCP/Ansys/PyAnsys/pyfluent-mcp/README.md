# PyFluent-MCP

[![PyAnsys](https://img.shields.io/badge/Py-Ansys-ffc107.svg?logo=data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAIAAACQkWg2AAABDklEQVQ4jWNgoDfg5+OQgMJ/0AqCqXGQMEBAwBEKQj5gGDjQsA80UeCDscxrD4YhGsgABEELnC5zAwAu6ACKQDAQzNBFwAAVdgFEAnfDiQAATyIBaAFgCbkAI5DQwAVGAYkAMA4gHgg2AC+AAgQIABggagAqyAD4AACkR7cEdcEBQOPjIvAEtRDoAbYLANQAZGsBEAFeBwCsAY0HgGCAAEQTaDj7xQABItJ+S3DsQAAAABJRU5ErkJggg==)](https://docs.pyansys.com/)
[![Python](https://img.shields.io/badge/Python-3.12%2B-blue)](https://www.python.org/)
[![Apache](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

PyFluent-MCP (`ansys-fluent-mcp`) gives you a [Model Context Protocol (MCP)](https://modelcontextprotocol.io/)
server that lets AI assistants interact with Ansys Fluent through
[PyFluent](https://fluent.docs.pyansys.com/).

PyFluent-MCP is built on PyAnsys Common MCP
([ansys-common-mcp](https://github.com/ansys/pyansys-common-mcp)), the shared
PyAnsys MCP foundation.

You can run this package as a standalone MCP server. It also serves as the
open-source **core + solve** foundation for higher-level products. Those
products depend on this package and call solve tools over MCP. Dependency
direction stays one-way. This package never depends on, imports, or
references products that consume it.

For architecture details, diagrams, and full tool references, see the
[PyFluent-MCP documentation](https://fluent-mcp.docs.pyansys.com). For contribution information, including how
to build documentation locally, see [Contribute](https://fluent-mcp.docs.pyansys.com/version/stable/getting_started/contribution.html).

## Overview

The server is a **stateless** MCP leaf. Your MCP host (VS Code Copilot,
Claude Desktop, Cursor, or a custom agent) calls a focused tool set. Fluent
mutations run only through validated MCP tools, and Python executes only
through a validated, sandboxed execution path.

Key features include:

- **Manage connections dynamically**: Launch a new Fluent session, attach to an
  existing session (local or remote), or disconnect on demand.
- **Inspect the live settings tree**: Explore the active Fluent settings API,
  named objects, allowed values, and targeted context.
- **Run code through a validated execution path**: Run or precheck Python in a persistent
  session behind an AST sandbox.
- **Review results and diagnostics**: Summarize setup, build a simulation
  report, inspect mesh quality, list fields, compare case files, and capture
  screenshots.
- **Extend with pluggable backends**: Use the local PyFluent backend by default
  and add execution backends through separately installed entry-point packages.

PyFluent-MCP itself is deterministic infrastructure. It does not own model
runtime selection, provider orchestration, transport policy, retries, or
agent loops. Those concerns live in higher-level host products such as
`fluids-mcp`, which consume this package over the MCP wire.

## Tool surface

You can use 20 tools exposed by the server:

| Group | Tools |
|-------|-------|
| Connection and session | `connect`, `disconnect`, `session_status`, `solver_status` |
| Schema discovery | `find_api`, `get_help`, `get_state`, `get_targeted_context` |
| Named objects | `list_named_objects`, `find_named_object`, `select_named_objects` |
| Execution and validation | `run_code`, `validate_code` |
| Reporting and inspection | `summarize_setup`, `simulation_report`, `screenshot` |
| Mesh/fields/compare | `mesh_quality`, `list_fields`, `compare_files` |

## Requirements

| Requirement | When needed | Notes |
|-------------|-------------|-------|
| Python 3.12 or later | Always | 3.12, 3.13, and 3.14 supported |
| Core runtime dependencies | Always (installed automatically) | `ansys-common-mcp`, `fastmcp`, `httpx`, `pydantic` |
| [PyFluent](https://fluent.docs.pyansys.com/) (`ansys-fluent-core` 0.27 or later) | To drive a live Fluent session (`connect`, `run_code`, `get_state`, `mesh_quality`, …) | Installed automatically as a required dependency |
| A licensed local ANSYS Fluent installation | To actually launch/attach a solver | PyFluent talks to this Fluent installation over gRPC |
| `h5py` 3.0 or later | Only for `compare_files` on `.h5`/`.cas.h5` files | The `file-probe` extra |

> **PyFluent is required for live-session tools and is installed automatically.**
> Offline-only tools such as `find_api`, `get_help`, and `validate_code`
> still work without a local Fluent installation. Any tool that touches a
> solver, including `connect`, `run_code`, `get_state`, `summarize_setup`,
> `mesh_quality`, and `screenshot`, requires a licensed Fluent installation
> on your machine.

## Installation

Install the latest release:

```bash
pip install ansys-fluent-mcp
```

To add the optional HDF5 file-probe support used by `compare_files`:

```bash
pip install "ansys-fluent-mcp[file-probe]"
```

If you want an editable developer installation with test dependencies:

```bash
git clone https://github.com/ansys/pyfluent-mcp.git
cd pyfluent-mcp
pip install -e ".[tests]"
```

## Usage

Use STDIO for desktop MCP clients that launch the server process. Use HTTP only on trusted networks or behind infrastructure that provides authentication and TLS.

Run the server over STDIO (the default MCP transport):

```bash
ansys-fluent-mcp
```

Or run the server over streamable HTTP:

```bash
ansys-fluent-mcp --transport http --host 127.0.0.1 --port 8000
```

Starting the MCP server only makes the tools available. You still need an
MCP-compatible client, such as VS Code Copilot, Claude Desktop, Cursor, or
another assistant host, to connect to it and call those tools. Register the
server in the client's MCP configuration after choosing a transport.

If you run a local Windows checkout, point your client at the virtual
environment entry point. For VS Code MCP support, add a server entry like this
to your VS Code MCP configuration:

```json
{
  "servers": {
    "ansys-fluent-mcp": {
      "type": "stdio",
      "command": "D:\\Development\\fluent\\pyfluent-mcp\\.venv\\Scripts\\ansys-fluent-mcp.exe"
    }
  }
}
```

## Configuration

You configure the server through `FLUIDS_MCP_*` environment variables. Common variables are listed here:

| Variable | Effect |
|----------|--------|
| `FLUIDS_MCP_SETTINGS_JSON` | Override the bundled settings schema with an external file |
| `FLUIDS_MCP_LOG_LEVEL` | Set the log level (default `INFO`) |
| `FLUIDS_MCP_DISABLE_SESSION_LOGS` | Set to `1` to disable session logs |
| `FLUIDS_MCP_MAX_STEPS` | Set a cap on MCP tool-loop iterations (default `30`) |

## Host ownership and architecture boundaries

`ansys-fluent-mcp` is the deterministic MCP substrate and solve leaf.
It intentionally does not own:

- model provider selection
- model routing
- transport orchestration
- caching policy
- retry management
- agent loops
- workflow reasoning

Those capabilities belong in higher-level orchestration products such as
`fluids-mcp`, VS Code Copilot agents, Claude Desktop workflows, or other
external MCP hosts.

This package focuses on:

- Fluent tool execution
- schema retrieval and grounding
- settings introspection
- validated Python execution
- deterministic MCP tooling
- backend abstractions

The architecture intentionally keeps dependency flow one-way:

```text
agent/orchestrator/runtime
            ↓
     ansys-fluent-mcp
```

The substrate never depends on the orchestration layer.

## License

This project is licensed under the Apache 2.0 license agreement. See the
[LICENSE](LICENSE) file for details.

## Resources

- [PyFluent documentation](https://fluent.docs.pyansys.com/)
- [Model Context Protocol](https://modelcontextprotocol.io/)
- [ansys-common-mcp](https://github.com/ansys/pyansys-common-mcp)

For general PyAnsys questions, email pyansys.core@ansys.com.
