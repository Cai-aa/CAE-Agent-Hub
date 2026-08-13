# Security

Default policy:

```text
workspace_only = true
allow_network = false
allow_arbitrary_shell = false
allow_arbitrary_python = false
```

Paths are canonicalized before use and must stay below the configured workspace. UNC paths are rejected. Output extensions are allowlisted by operation.

External process calls use `shell=False`, argument arrays, bounded timeouts, dedicated stdout/stderr logs, and a fixed executable-name whitelist. No MCP tool accepts a command line, executable, Python source, macro, module name, or shell fragment.

FreeCAD executes only the repository's fixed macro/runner pair. ParaView accepts only the worker methods implemented in `bridge_worker.py`. The Elmer SIF engine only emits the verified `heat_steady_v1` keyword profile; raw SIF mode is absent in v0.1.

Every modifying or native operation records tool inputs/results, process metadata, generated artifacts, and SHA-256 hashes beneath the project `evidence/` directory.

