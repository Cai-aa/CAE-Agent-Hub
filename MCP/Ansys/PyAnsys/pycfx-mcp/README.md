# Ansys CFX-MCP

[![PyAnsys](https://img.shields.io/badge/Py-Ansys-ffc107.svg?logo=data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAIAAACQkWg2AAABDklEQVQ4jWNgoDfg5+OQgMJ/0AqCqXGQMEBAwBEKQj5gGDjQsA80UeCDscxrD4YhGsgABEELnC5zAwAu6ACKQDAQzNBFwAAVdgFEAnfDiQAATyIBaAFgCbkAI5DQwAVGAYkAMA4gHgg2AC+AAgQIABggagAqyAD4AACkR7cEdcEBQOPjIvAEtRDoAbYLANQAZGsBEAFeBwCsAY0HgGCAAEQTaDj7xQABItJ+S3DsQAAAABJRU5ErkJggg==)](https://docs.pyansys.com/)
[![Python](https://img.shields.io/badge/Python-3.12%2B-blue)](https://www.python.org/)
[![Apache](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

Ansys CFX-MCP (`ansys-cfx-mcp`) is a [Model Context Protocol (MCP)](https://modelcontextprotocol.io/)
server that enables AI assistants to interact with Ansys CFX through
[PyCFX](https://pypi.org/project/ansys-cfx-core/). It enables
natural-language-assisted CFX-Pre, CFX Solver, and CFD-Post workflows for
setup, execution, and postprocessing.

It is built on PyAnsys Common MCP ([ansys-common-mcp](https://github.com/ansys/pyansys-common-mcp)),
the shared PyAnsys MCP foundation.

This package is **self-contained** and works as a **standalone** server for any MCP host.
It exposes a compact CFX-oriented tool surface so you can connect to CFX sessions,
inspect bounded model context, validate and run reviewed PyCFX snippets, and
coordinate common solver and CFD-Post actions.

For quick-start, configuration, architecture, examples, and per-tool reference
material, see the [PyCFX-MCP documentation](https://cfx-mcp.docs.pyansys.com).

## Overview

Ansys CFX-MCP is a **stateless** MCP leaf. MCP clients such as Visual Studio
Code Copilot, Claude Desktop, Cursor, or a custom automation host call a focused
set of tools to drive live CFX-Pre, CFD-Post, and CFX Solver sessions. Custom
Python runs through a validated, Python-level restricted execution path. This is
not an operating-system or container sandbox.

Key features:

- **CFX session management**: Start or attach to CFX-Pre, CFX Solver, and
  CFD-Post workflows.
- **Workflow routing**: Use one compact `cfx_workflow` tool for common CFX
  lifecycle actions.
- **Bounded model context**: Inspect summaries, named objects, API help,
  allowed values, and selected state snippets without dumping entire models
  into an MCP client.
- **Validated execution**: Run custom snippets in a persistent PyCFX execution context
  with strict AST validation, guarded imports, and limited built-in functions.
- **Flexible MCP transport**: Run over STDIO for local clients or Streamable
  HTTP for trusted local integrations.

## Tool surface

The default MCP surface includes seven tools:

| Group | Tools |
|-------|-------|
| Connection and session | `connect`, `disconnect`, and `session_status` |
| CFX workflow routing | `cfx_workflow` |
| Bounded model context | `cfx_model_context` |
| Code execution | `run_code` and `validate_code` |

The server also exposes a `toolsets://definition` MCP resource for clients or
conductors that group related tools. The default CFX toolsets cover connection
management, CFX workflow routing, CFX model context, and code execution.

## Requirements

| Requirement | When needed | Notes |
|-------------|-------------|-------|
| **Python 3.12** or later | Always | 3.12, 3.13 and 3.14 are supported |
| **Core runtime dependencies** | Always (installed automatically) | `ansys-common-mcp`, `fastmcp`, `pydantic`, and `requests` |
| **A licensed local Ansys CFX installation** | To launch or attach CFX tools | Required for workflows that use CFX-Pre, CFX Solver, or CFD-Post |

> **PyCFX and Ansys CFX are required for live-session tools.** Any tool that
> touches a CFX app (`connect`, `run_code`, `cfx_workflow`,
> `cfx_model_context`, and `session_status`) requires `ansys-cfx-core` and a
> licensed CFX installation on your machine.

## Installation

Install the latest release for users:

```bash
pip install ansys-cfx-mcp
```

Install the latest release for developers:

```bash
git clone https://github.com/ansys/pycfx-mcp.git
cd pycfx-mcp
pip install -e ".[dev,doc]"
```

## Usage

Run PyCFX-MCP over STDIO, the default transport for desktop MCP clients:

```bash
ansys-cfx-mcp --transport stdio
```

Or, run PyCFX-MCP over Streamable HTTP:

```bash
ansys-cfx-mcp --transport http --host 127.0.0.1 --port 8000
```

Use STDIO for desktop MCP clients that launch the server process. Use
Streamable HTTP only on trusted networks or behind infrastructure that
provides authentication and TLS.

Starting PyCFX-MCP only makes the tools available. You still need an
MCP-compatible client, such as Visual Studio Code Copilot, Claude Desktop,
Cursor, or another assistant host, to connect to PyCFX-MCP. For more information, see
[IDE and client configuration](https://cfx-mcp.docs.pyansys.com/version/stable/getting_started/ide_configuration.html) in the PyCFX-MCP documentation.

## Configuration

The standalone server does not call a language model. Configure only the server
transport, logging, and backend options needed for your MCP client. Custom code
authoring belongs in the MCP host or a higher-level agent layer; PyCFX-MCP
validates and runs reviewed Python through `validate_code` and `run_code`.

For transport settings, see
[Configuration](https://cfx-mcp.docs.pyansys.com/version/stable/user_guide/configuration.html) in the PyCFX-MCP documentation.

## License

This project is licensed under the Apache License, Version 2.0. See the
[LICENSE](LICENSE) file for details.

## Resources

- [PyCFX-MCP documentation](https://cfx-mcp.docs.pyansys.com/)
- [PyCFX package](https://pypi.org/project/ansys-cfx-core/)
- [PyAnsys documentation](https://docs.pyansys.com/)
- [Model Context Protocol documentation](https://modelcontextprotocol.io/)
- [FastMCP documentation](https://github.com/jlowin/fastmcp)
- [Ansys CFX product information](https://www.ansys.com/products/fluids/ansys-cfx)
- [PyCFX-MCP Issues page](https://github.com/ansys/pycfx-mcp/issues)
- [PyCFX-MCP Discussions page](https://github.com/ansys/pycfx-mcp/discussions)

For general PyAnsys questions, email [pyansys.core@ansys.com](mailto:pyansys.core@ansys.com).
