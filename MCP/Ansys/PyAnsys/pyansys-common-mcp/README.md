# PyAnsys Common MCP

[![PyAnsys](https://img.shields.io/badge/Py-Ansys-ffc107.svg?logo=data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAIAAACQkWg2AAABDklEQVQ4jWNgoDfg5+OQgMJ/0AqCqXGQMEBAwBEKQj5gGDjQsA80UeCDscxrD4YhGsgABEELnC5zAwAu6ADCKQDAQzNBFwAAVdgFEAnfDiQAATyIBaAFgCbkAI5DQwAVGAYkAMA4gHgg2AC+AAgQIABggagAqyAD4AF0MaB8gCbgoEAL0MEYRz4WxpMdWFzQBYKhK8DjEYH9KDgAw9ACAAgwFCgC2AMJvgAAJv+LQQJwJ8AAKQEoAAxr7W4AG/wGqAB4AACkR7cEdcEBQOPjIvAEtRDoAbYLANQAZGsBEAFeBwCsAY0HgGCAAEQTaDj7xQAABItJ+S3DsQAAAABJRU5ErkJggg==)](https://docs.pyansys.com/)
[![Python](https://img.shields.io/pypi/pyversions/ansys-common-mcp?logo=pypi)](https://pypi.org/project/ansys-common-mcp)
[![Apache](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

PyAnsys Common MCP provides the infrastructure for building [Model Context Protocol (MCP)](https://modelcontextprotocol.io/) servers for PyAnsys libraries.

## Overview

This package provides the foundation for creating MCP servers that enable AI assistants (like Claude, ChatGPT) to interact with Ansys products through PyAnsys libraries.

**Key features:**
- **Persistent Python sessions**: Maintains stateful code execution across multiple AI requests.
- **Lifecycle management**: Handles startup, cleanup, and errors automatically.
- **Extensible architecture**: Uses base classes and patterns for product-specific implementations.
- **Logging infrastructure**: Uses pre-configured logging that does not interfere with the MCP protocol.

## Installation

### For users

The ``ansys.common.mcp`` package currently supports Python 3.12 through
Python 3.14 on Windows, Mac OS, and Linux.

Install the latest package for use with this command:

```bash
pip install ansys-common-mcp
```

Alternatively, install the latest
[PyAnsys Common MCP GitHub](https://github.com/ansys/pyansys-common-mcp) package
with this command:

```bash
pip install git+https://github.com/ansys/pyansys-common-mcp.git
```

### For developers

If you are contributing to PyAnsys Common MCP or creating custom servers, install the package in developer mode:

```bash
# Clone the repository
git clone https://github.com/ansys/pyansys-common-mcp.git
cd pyansys-common-mcp

# Install in editable mode with development dependencies
pip install -e .[dev]

# Or install documentation dependencies for building documentation
pip install -e .[doc]
```

## Quick start

To create an MCP server for your PyAnsys library, follow these three main steps:

1. **Define your custom context**: Extend the `PyAnsysBaseAppContext` dataclass to store the product-specific state.
2. **Implement your MCP server**: Extend the `PyAnsysBaseMCP` base class with startup and cleanup logic.
3. **Create MCP tools**: Define tools that interact with your product.

## Real-world example

For a complete, production-ready implementation, see the [PyMAPDL-MCP](https://github.com/ansys/pymapdl-mcp) repository.

## Resources

- [PyAnsys Common MCP documentation](https://common-mcp.docs.pyansys.com)
- [Repository's Issues page](https://github.com/ansys/pyansys-common-mcp/issues)
- [Repository's Discussion page](https://github.com/ansys/pyansys-common-mcp/discussions)

For general PyAnsys questions, email pyansys.core@ansys.com.
