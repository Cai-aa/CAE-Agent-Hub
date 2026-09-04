<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/ansys/pyaedt-mcp/main/doc/source/_static/images/logo-dark.png">
    <source media="(prefers-color-scheme: light)" srcset="https://raw.githubusercontent.com/ansys/pyaedt-mcp/main/doc/source/_static/images/logo-light.png">
    <img alt="PyAEDT-MCP" src="https://raw.githubusercontent.com/ansys/pyaedt-mcp/main/doc/source/_static/images/logo-light.png" width="900">
  </picture>
</p>

[![PyAnsys](https://img.shields.io/badge/Py-Ansys-ffc107.svg?logo=data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAIAAACQkWg2AAABDklEQVQ4jWNgoDfg5mD8vE7q/3bpVyskbW0sMRUwofHD7Dh5OBkZGBgW7/3W2tZpa2tLQEOyOzeEsfumlK2tbVpaGj4N6jIs1lpsDAwMJ278sveMY2BgCA0NFRISwqkhyQ1q/Nyd3zg4OBgYGNjZ2ePi4rB5loGBhZnhxTLJ/9ulv26Q4uVk1NXV/f///////69du4Zdg78lx//t0v+3S88rFISInD59GqIH2esIJ8G9O2/XVwhjzpw5EAam1xkkBJn/bJX+v1365hxxuCAfH9+3b9/+////48cPuNehNsS7cDEzMTAwMMzb+Q2u4dOnT2vWrMHu9ZtzxP9vl/69RVpCkBlZ3N7enoDXBwEAAA+YYitOilMVAAAAAElFTkSuQmCC)](https://docs.pyansys.com/)
[![Python](https://img.shields.io/badge/python-3.12%2B-blue.svg)](https://www.python.org/)
[![License: Apache%202.0](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

PyAEDT-MCP is an MCP (Model Context Protocol) server for Ansys Electronics Desktop (AEDT). It gives you reliable AEDT tools and a persistent PyAEDT-backed Python session for tasks that do not fit a dedicated tool.

## What PyAEDT-MCP does

PyAEDT-MCP supports this runtime loop:

1. Check whether AEDT is installed or already reachable.
2. Launch AEDT or connect to an existing gRPC session.
3. Open projects, create designs, run analyses, inspect the model, and export results.
4. Use `run_python_code` or `run_python_script` for custom PyAEDT work.

Supported AEDT applications include HFSS, Maxwell 2D/3D, Q2D, Q3D, Icepak, Circuit, TwinBuilder, Mechanical, EMIT, RMXprt, and HFSS 3D Layout.

## Install

### Run without cloning

Install [uv](https://docs.astral.sh/uv/getting-started/installation/) first.
It includes `uvx`, which downloads and runs PyAEDT-MCP without cloning the
repository.

```bash
uvx --from git+https://github.com/ansys/pyaedt-mcp.git ansys-aedt-mcp
```

### Install locally

```bash
pip install git+https://github.com/ansys/pyaedt-mcp.git
```

Or use `uv`:

```bash
uv pip install git+https://github.com/ansys/pyaedt-mcp.git
```

### Install for development

```bash
git clone https://github.com/ansys/pyaedt-mcp.git
cd pyaedt-mcp
pip install -e .
pre-commit install
```

Or use `uv`:

```bash
git clone https://github.com/ansys/pyaedt-mcp.git
cd pyaedt-mcp
uv pip install -e .
pre-commit install
```

## Requirements

- Python 3.12 or later
- AEDT 2022 R2 or later for gRPC workflows
- A local AEDT installation or a reachable remote AEDT gRPC endpoint

## Quick start

1. Start AEDT in gRPC mode when connecting to an existing session:

   ```bash
   "C:\Program Files\ANSYS Inc\v261\AnsysEM\ansysedt.exe" -grpcsrv 50051
   ```

   Or, just launch AEDT normally. It automatically starts a gRPC server.

   > PyAEDT-MCP can also launch AEDT for you if it is not already running.

2. Choose an MCP transport:

   - **stdio** is the simplest option for one local client. The client starts
     PyAEDT-MCP automatically through `uvx` or from a cloned repository's
     virtual environment.
   - **HTTP** connects the client to a separately running server. Use it for
     local development, Docker, or a remote server.

   Start an HTTP server through `uvx` without cloning:

   ```bash
   uvx --index-strategy unsafe-best-match \
     --from git+https://github.com/ansys/pyaedt-mcp.git ansys-aedt-mcp \
     --transport http --http-host 127.0.0.1 --http-port 8080
   ```

3. Point an MCP client at the server:

   Use the [IDE and client configuration guide](https://aedt-mcp.docs.pyansys.com/version/dev/getting_started/ide_configuration.html)
   for short HTTP and stdio configurations for VS Code/Copilot, Claude,
   OpenCode, and Codex, plus local virtual-environment instructions.

## Tool reference

For information on the available tools, see [Tools and capabilities](https://aedt-mcp.docs.pyansys.com/version/dev/user_guide/tools_and_capabilities.html) in the PyAEDT-MCP documentation.

## How the repository is organized

The core package is in `src\ansys\aedt\mcp`:

| File | Role |
| --- | --- |
| `__main__.py` | Module entry point that forwards to the CLI launcher |
| `server.py` | CLI parsing, app setup, context creation, startup cleanup, and transport selection |
| `tools.py` | Runtime tool implementations for AEDT lifecycle, project, scripting, and export workflows |
| `helpers.py` | Small utilities for probing endpoints, normalizing versions, and extracting model data |
| `prompts.py` | System prompt content shown to MCP clients |
| `contexts.py` | Optional context helper tools enabled by `--include-context` |
| `toolsets.py` | `toolsets://definition` resource used for logical tool discovery |
| `aedt_helper\startup_code.py` | Startup code loaded into the persistent Python session |

Other top-level folders include:

- `doc\source`: Sphinx documentation
- `tests`: Unit and integration coverage
- `docker`: Container assets
- `examples`: Sample assets used by the project

## Development workflow

To contribute, see [Contribute](https://aedt-mcp.docs.pyansys.com/version/dev/getting_started/contribution.html) in the PyAEDT-MCP documentation.

## Add a new tool

Most tools require a live AEDT connection. Tag those tools with `REQUIRES_AEDT_TAG` in `src\ansys\aedt\mcp\tools.py` so they can be hidden until the session exists when dynamic discovery is enabled.

For more information, see [Add a new tool](https://aedt-mcp.docs.pyansys.com/version/dev/examples/adding_new_tool.html) in the PyAEDT-MCP documentation.

## License

Apache 2.0 license. See [LICENSE](LICENSE).

## Related projects

- [PyAEDT](https://github.com/ansys/pyaedt)
- [PyAEDT documentation](https://aedt.docs.pyansys.com/)
- [FastMCP documentation](https://github.com/jlowin/fastmcp)
- [Model Context Protocol documentation](https://modelcontextprotocol.io/)
