# PyLumerical MCP Server

[![PyAnsys](https://img.shields.io/badge/Py-Ansys-ffc107.svg?logo=data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAIAAACQkWg2AAABDklEQVQ4jWNgoDfg5+OQgMJ/0AqCqXGQMEBAwBEKQj5gGDjQsA80UeCDscxrD4YhGsgABEELnC5zAwAu6ACKQDAQzNBFwAAVdgFEAnfDiQAATyIBaAFgCbkAI5DQwAVGAYkAMA4gHgg2AC+AAgQIABggagAqyAD4AACkR7cEdcEBQOPjIvAEtRDoAbYLANQAZGsBEAFeBwCsAY0HgGCAAEQTaDj7xQABItJ+S3DsQAAAABJRU5ErkJggg==)](https://docs.pyansys.com/)
[![Python](https://img.shields.io/badge/Python-3.12%2B-blue)](https://www.python.org/)
[![Apache](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

PyLumerical MCP Server provides a [Model Context Protocol (MCP)](https://modelcontextprotocol.io/)
server that enables AI assistants to interact with Ansys Lumerical (FDTD, MODE,
DEVICE, INTERCONNECT) through
[PyLumerical](https://github.com/ansys/pylumerical). This server enables
natural language interaction with Lumerical for photonics and electromagnetic
simulation workflows.

## Overview

Key features:

- **Multi-session management**: Open, list, and close multiple concurrent
  Lumerical sessions (FDTD, MODE, DEVICE, INTERCONNECT) under user-chosen names.
- **Persistent Python execution**: Run arbitrary Python and PyLumerical code
  against live Lumerical handles, with state preserved across tool calls.
- **Workflow guidance**: Access context and best practices for Lumerical simulations.
- **Cross platform support**: Enable Windows and Linux support with headless CAD.

## Prerequisites

- Python 3.12, 3.13, or 3.14
- Ansys Lumerical installation
- Ansys Lumerical license

## Installation

### For users

Install the latest release with:

```bash
pip install ansys-lumerical-mcp
```

Or run directly without installing using [`uvx`](https://docs.astral.sh/uv/):

```bash
uvx --from git+https://github.com/ansys/pylumerical-mcp ansys-lumerical-mcp
```

### For developers

#### Install

```bash
# Clone the repository
git clone https://github.com/ansys/pylumerical-mcp.git
cd pylumerical-mcp

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate or .venv\Scripts\Activate.ps1
pip install uv

# Install dependencies
uv sync

# Run
uv run ansys-lumerical-mcp
```

#### Quick start with VS Code or Cursor
If you're using the devopment container:
```jsonc
{
	"servers": {
		"pylumerical-mcp": {
			"type": "stdio",
			"command": "/workspaces/pylumerical-mcp/.venv/bin/ansys-lumerical-mcp",
			"args": []
		}
	},
	"inputs": []
}
```

## Usage

For step-by-step setup instructions for VS Code, Claude Code, Claude Desktop,
Cursor, and other MCP-compatible clients, follow your client's documentation.

## License

This project is licensed under the Apache 2.0 license agreement. See the [LICENSE](./LICENSE) file for details.

## Resources

- [PyLumerical-MCP documentation](https://lumerical-mcp.docs.pyansys.com)
- [PyLumerical documentation](https://github.com/ansys/pylumerical)
- [Model Context Protocol](https://modelcontextprotocol.io/)
- [FastMCP documentation](https://github.com/jlowin/fastmcp)
- [Ansys Lumerical](https://www.ansys.com/products/photonics)
- [Repository's Issues page](https://github.com/ansys/pylumerical-mcp/issues)
- [Repository's Discussions page](https://github.com/ansys/pylumerical-mcp/discussions)

For general PyAnsys questions, email [pyansys.core@ansys.com](mailto:pyansys.core@ansys.com).
