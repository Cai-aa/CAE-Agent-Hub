---
name: cfx-mcp-tools
description: 'Use when: operating the standalone ansys-cfx-mcp CFX MCP leaf directly from generic clients or MCP hosts. Covers CFX-Pre, Solver, CFD-Post, cfx_workflow, cfx_model_context, run_code, validate_code, lifecycle actions, model context, named objects, API help, and result-file discovery.'
argument-hint: 'Describe the CFX task and available MCP tools'
---

# PyCFX-MCP tools

Use this skill when you are calling the standalone `ansys-cfx-mcp` CFX MCP leaf directly. The CFX leaf intentionally exposes a small tool surface so generic agents do not have to choose among many low-level helpers.

## Tool surface

Expect these tools by default:

- `session_status`
- `connect`
- `disconnect`
- `cfx_workflow`
- `cfx_model_context`
- `run_code`
- `validate_code`

Do not assume direct MCP access to low-level helper names such as `list_named_objects`, `get_state`, `find_api`, `get_help`, `solver_status`, or `summarize_setup`. Use `cfx_model_context` or `cfx_workflow` instead.

For exact action names and parameter shapes, load [tool reference](./references/cfx-mcp-tool-reference.md).

## Operating pattern

1. Call `session_status` first to learn whether CFX-Pre, Solver, or CFD-Post is already connected.
2. Use `connect` or `cfx_workflow(action="start_pre")` to start or attach to CFX-Pre when setup/model work is needed. Prefer an explicit `connect` `mode` (`"launch"` to start locally, `"attach"` to join a running server) so intent is unambiguous. `mode="auto"` (the default) infers it from the parameters.
3. Use `cfx_model_context` for bounded model inspection. Request one slice at a time, such as a summary, named-object lookup, API help entry, or targeted context.
4. Use `cfx_workflow` for lifecycle and artifact steps: import mesh, write `.def`, start solver, wait for solver, get `.res`, or open CFD-Post.
5. Use `validate_code` for explicit CFX Python snippets that are not covered by the routed workflow actions.
6. Use `run_code` only for safe, intentional inspection or edits requested by the user. Prefer read-only inspection first.
7. Call `disconnect` when the user asks to close the session or when cleaning up a dedicated run.

## Token discipline

Keep context calls narrow. `cfx_model_context` accepts `max_items`. Use small values such as `10` or `20` unless the user explicitly asks for more. Do not dump the full model tree into the chat.

## Safety rules

- Never invent CFX object paths or command signatures. Use `cfx_model_context(action="api_help")`, `cfx_model_context(action="find_api")`, or targeted context first.
- Do not use paths or assumptions from other products for CFX.
- Do not treat `cfx_workflow` as a free-form macro executor. It only accepts supported lifecycle/artifact actions.
- For solver launch requests, prefer `cfx_workflow(action="start_solver")`, then `cfx_workflow(action="wait_solver")`, then `cfx_workflow(action="get_results_file")`.
- For custom setup changes, validate explicit PyCFX-oriented code, and then run it only after the user intent is clear.

## Common recipes

Start CFX-Pre and import a mesh:

```text
1. session_status
2. cfx_workflow(action="start_pre", params={})
3. cfx_workflow(action="import_mesh", params={"path": "C:\\path\\mesh.gtm"})
4. cfx_model_context(action="summary", max_items=20)
```

Launch a solver from an existing `.def` file and find the result file:

```text
1. cfx_workflow(action="start_solver", params={"input_file": "C:\\path\\case.def", "mode": "serial"})
2. cfx_workflow(action="wait_solver", params={"timeout": 3600})
3. cfx_workflow(action="get_results_file", params={})
```

Inspect a named object without dumping the model:

```text
1. cfx_model_context(action="find_named_object", params={"query": "inlet"}, max_items=10)
2. cfx_model_context(action="targeted_context", params={"paths_to_check": ["FLOW: Flow Analysis 1"], "named_object_types": ["boundary"]}, max_items=20)
```
