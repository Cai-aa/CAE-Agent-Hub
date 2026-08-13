# FEP Agent Hub Agent Instructions

1. Read `README.zh-CN.md` and the relevant file under `docs/` before changing a solver workflow.
2. Resolve executables from `OPEN_CAE_CONFIG`, environment variables, or `configs/open-cae.local.toml`. Treat public example paths as placeholders.
3. Keep generated models, meshes, logs, solver outputs, images, and evidence under the configured `workspace/` project directory.
4. Do not expose arbitrary shell, arbitrary Python, `eval`, or arbitrary executable tools.
5. Never claim solver success from file presence alone. Check process exit, logs, expected artifacts, finite fields, and case-specific physics gates.
6. A capability that is intentionally unsupported must return `BLOCKED` with a recommended next action; never fabricate an artifact.
7. Public files must not contain author-machine paths, commercial manuals, private models, license data, or large generated results.
8. Before release, run `pytest`, `scripts/protocol_smoke.py`, the native heat smoke, and `scripts/mcp_full_validation.py`.
