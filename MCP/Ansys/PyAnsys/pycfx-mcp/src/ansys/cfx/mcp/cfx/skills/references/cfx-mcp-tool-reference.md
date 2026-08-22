# PyCFX-MCP tool reference

This reference is for the direct `CFXMCP` leaf. It is not the Setup Agent API.

## Default tools

| Tool | Use |
|------|-----|
| `session_status` | Check connection state and current product/session metadata. |
| `connect` | Start or attach to a CFX product session. |
| `disconnect` | Close active CFX sessions managed by the backend. |
| `cfx_workflow` | Route lifecycle and artifact operations through a small action enum. |
| `cfx_model_context` | Route bounded model/API/context inspection through a small action enum. |
| `run_code` | Execute generated or user-approved Python against the CFX backend context. |
| `validate_code` | Validate Python before execution. |

## `connect`

Starts a new local CFX session (**launch**) or attaches to an already-running
server (**attach**). One call may target CFX-Pre, the Solver, and CFD-Post via
their respective parameters.

| Param | Use |
|-------|-----|
| `mode` | Optional. `"auto"` (default) infers launch versus attach from the other parameters. `"launch"` forces a local launch and rejects attach parameters. `"attach"` requires attach parameters. |
| `ip`, `port`, `password` | Attach to a running CFX-Pre/CFD-Post server. |
| `server_info_file` / `pre_sinfo` | `.sinfo` file to attach to CFX-Pre. |
| `post_sinfo` / `post_server_info_file` | `.sinfo` file to attach to CFD-Post. |
| `case_file_name` / `project_file` | `.cfx` project to open when launching CFX-Pre. |
| `solver_input_file` | `.def` file to launch the Solver with (launch only). |
| `results_file` | `.res` file to open when launching CFD-Post. |
| `launcher`, `ui_mode`, `product_version`, `start_timeout`, `additional_arguments`, `container_dict`, `cleanup_on_exit` | Optional launch tuning. |

Backward compatibility: Omitting `mode` (or `mode="auto"`) preserves the prior
inferred behavior. Set `mode` explicitly to fail fast on a mismatched
parameter set instead of silently launching/attaching unexpectedly.

Examples:

```json
{"mode": "launch"}
```

```json
{"mode": "attach", "ip": "127.0.0.1", "port": 12345}
```

## `cfx_workflow`

Signature:

```python
cfx_workflow(action: str, params: dict | None = None) -> dict
```

Supported actions:

| Action | Required or useful parameters | Result |
|--------|---------------------------|--------|
| `status` or `session_status` | None | Returns solver/session status. |
| `start_pre` | Optional connection kwargs | Starts or attaches to CFX-Pre. |
| `import_mesh` | `path` | Imports a mesh through CFX-Pre. |
| `write_def` | `path` | Writes a solver input `.def` file. |
| `start_solver` | `input_file` or `def_file`, optional `mode`, optional connection kwargs | Starts or attaches to CFX Solver for the input file. |
| `wait_solver` | Optional `timeout` | Waits for the active solver run to complete. |
| `get_results_file` | None | Returns the remembered or discovered `.res` file. |
| `open_post` | `result_file` or `res_file`, optional connection kwargs | Starts or attaches to CFD-Post for a result file. |

Parameter aliases:

- `import_mesh`: `path`, `mesh_file`, or `mesh`
- `write_def`: `path`, `def_file`, or `output_file`
- `start_solver`: `input_file` or `def_file`
- `open_post`: `result_file` or `res_file`

Recommended solver workflow:

```json
{"action": "start_solver", "params": {"input_file": "C:\\Users\\name\\case.def", "mode": "serial"}}
```

Then:

```json
{"action": "wait_solver", "params": {"timeout": 3600}}
```

Then:

```json
{"action": "get_results_file", "params": {}}
```

## `cfx_model_context`

Signature:

```python
cfx_model_context(action: str = "summary", params: dict | None = None, max_items: int = 20) -> dict
```

`max_items` is clamped by the backend. Use small values for generic-agent calls.

Supported actions:

| Action | Parameters | Result |
|--------|--------|--------|
| `summary` | None | Compact CFX-native setup/session summary. |
| `list_named_objects` | optional `types` | Named-object names grouped by type. |
| `find_named_object` | `query`, optional `types` | Matching named objects. |
| `select_named_objects` | optional `types`, optional `filters` | Filtered named-object selection. |
| `state` | `paths` | Values for selected CFX state/API paths. |
| `api_help` | `path` | Help and allowed values for one path. |
| `find_api` | `query`, optional `limit` | Static CFX API/catalog matches. |
| `allowed_values` | `path` | Allowed values for one path. |
| `targeted_context` | optional `paths_to_check`, `named_object_types`, `instance_state_fetch` | Batched targeted context for planning. |

Examples:

```json
{"action": "summary", "params": {}, "max_items": 20}
```

```json
{"action": "find_named_object", "params": {"query": "inlet", "types": ["boundary"]}, "max_items": 10}
```

```json
{"action": "api_help", "params": {"path": "FLOW: Flow Analysis 1"}, "max_items": 20}
```

```json
{
  "action": "targeted_context",
  "params": {
    "paths_to_check": ["FLOW: Flow Analysis 1"],
    "named_object_types": ["boundary", "domain"],
    "instance_state_fetch": true
  },
  "max_items": 20
}
```

## When to use code execution

Use `validate_code` and `run_code` when the requested operation is a custom model edit or detailed inspection that cannot be represented by `cfx_workflow` or `cfx_model_context`.

Good explicit-code tasks:

- Create or edit a CFX-Pre boundary condition after enough model context is known.
- Inspect a small set of CFX objects using PyCFX APIs.
- Prepare a custom CFD-Post export after opening a result file.

Avoid code execution when a routed action exists. For example, do not write custom Python to wait for solver completion. Call `cfx_workflow(action="wait_solver")`.

## Direct CFX MCP tools versus Setup Agent

Direct CFX MCP tools execute immediately. They do not build a pending Apply plan. For chat-style planning, validation, and explicit Apply semantics, use the Setup Agent instead of the CFX leaf.
