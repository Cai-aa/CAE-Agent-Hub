# ANSA MCP

[中文说明](README.zh-CN.md)

## Runtime UI patch 0.5.1

[Download the portable plugin](dist/ANSA_MCP_Bridge-0.5.1-release/ANSA_MCP_Bridge-0.5.1.bpkg)
for the narrower, scrollable Runtime panel. [Changes and validation limits](RELEASE_0.5.1.md).
Save your model and restart ANSA after installation. External MCP tools are unchanged.

## Download 0.5.0

- [Portable plugin for third-party Windows users](dist/ANSA_MCP_Bridge-0.5.0-release/ANSA_MCP_Bridge-0.5.0.bpkg)
- [Machine-specific upgrade requested by the original workstation owner](dist/ANSA_MCP_Bridge-0.5.0-upgrade/ANSA_MCP_Bridge-0.5.0.bpkg)
- [Package selection, installation and SHA-256 checks](dist/README.md) · [Release validation](RELEASE_0.5.0.md)

Install the external MCP and shared authentication configuration first using the
steps below. Installing the plugin alone does not configure the MCP client.

### General-purpose Windows release 0.5.0

Default: **18 generic MCP tools**; the eight cantilever tools are disabled.
The named operation catalog now contains **24 actions**, including scoped geometry cleanup,
meshing/quality repair, materials/references, Abaqus loads/constraints/contact and flat solver I/O.
See [engineering operations and real validation limits](ENGINEERING_OPERATIONS.md).
See [general operations and compatibility](GENERAL_OPERATIONS.md) for the exact
operation catalog, API discovery, deployment and validation boundaries. This is
not a guarantee of all ANSA APIs or all ANSA versions. Python >=3.9 is required
inside ANSA; the external MCP process requires Python >=3.10.

The native package now bundles the dashboard: connection/session overview,
100-request timeline, before/after count snapshots and redacted diagnostic exports.
See the [plugin installation, upgrade and MCP client guide](plugin/README.md).
Save the model and restart ANSA after upgrading to discard cached Python modules.
API returns, count changes and engineering validation are separate evidence;
long GUI-thread calls cannot guarantee intermediate panel updates.

ANSA MCP is a local FastMCP server for controlled access to a running BETA CAE
Systems ANSA session. It uses an external Python MCP process plus a small Python
bridge that the user explicitly loads inside ANSA. The first release focuses on
session/model inspection, bounded model checks, and confirmed model changes.
It now also offers an explicitly confirmed **arbitrary Python step** in the
current ANSA GUI process for different simulation workflows. This tool is not
sandboxed and has ANSA's local privileges: review every script before calling it.
Opt-in example tools run a fixed cantilever example in a separate ANSA batch
process and Abaqus/Standard.

For an opt-in teaching run in the already-open ANSA GUI, use the separate fixed-demo
`*_visible_cantilever_static_demo` tools described below. They import a
SHA-256-pinned mesh into an empty live ANSA model, fit and redraw it, then
save/export from that session. The bridge window shows workflow phases.
Abaqus/Standard still solves externally; ANSA does not display its internal
iterations or ODB contours.

For any other model, split the AI workflow into multiple typed tool calls or
`execute_live_ansa_python_step` calls. After each mutating call, the bridge
requests `RedrawAll()` on ANSA's GUI thread, updates its control window, and
records the step. `get_live_step_history` reads the latest 100 steps. Internal
actions in one long script, external solver iterations, and META postprocessing
are not automatically shown frame by frame in ANSA.

The development target on this workstation is ANSA v25.1.2. Compatibility with
another ANSA release must be established with the live probes and an actual
model; detecting an installation directory is not compatibility evidence.

## Architecture at a glance

```text
Codex / another MCP client
          | MCP over stdio
          v
external `ansa_mcp` FastMCP process
          | mutually authenticated HMAC, newline-delimited JSON
          | 127.0.0.1:48762 only
          v
`ansa_plugin/start_ansa_mcp.py` loaded inside ANSA
          | visible "ANSA MCP Bridge" control window
          | blocking `BCShow` keeps the loaded script alive
          | 25 ms GUI `BCTimer` + non-blocking socket reactor
          | named method allowlist (including confirmed arbitrary Python steps)
          v
current ANSA Python API / database
```

Both processes read `%LOCALAPPDATA%\ANSAMCP\bridge.json`. The file contains a
random token, the loopback endpoint, and file roots permitted for bridge file
operations. Keep it private. See [ARCHITECTURE.md](ARCHITECTURE.md) for protocol,
trust-boundary, and failure-state details.

The bridge may also write `%LOCALAPPDATA%\ANSAMCP\status.json`, but that file is
only a diagnostic lifecycle snapshot and is never authoritative evidence of
liveness. Only a current authenticated `probe_live_bridge.py` result or live
`ping` proves that a bridge is responding.

The snapshot progresses from `starting` after bind/timer setup to `online` only
after the first successful timer callback on the ANSA main thread; closing the
control window writes `offline`. A stale `online` file is still not proof. Match
the authenticated ping's process ID and callback thread identity to the intended
ANSA session.

## Safety properties

- The bridge is required to bind to `127.0.0.1`; non-loopback configuration is
  rejected.
- Windows requires exclusive listener ownership with `SO_EXCLUSIVEADDRUSE` and
  never enables Winsock `SO_REUSEADDR`, so no second listener can share the port
  after the bridge binds it. A process that bound first still cannot impersonate
  the bridge without proving knowledge of the credential.
- Wire protocol v3 starts with a nonsensitive, fresh client nonce. The server
  binds that nonce and its own fresh challenge into HMAC-SHA-256 proofs for the
  server hello, client request, and server response. The client verifies the
  server before sending method/parameters, recorded hellos cannot be replayed to
  solicit a request, and the 64-hex credential is never placed on the wire.
- Only named bridge methods are dispatched, but `execute_python_step` permits
  **arbitrary Python**, including imports, filesystem access, and process
  launches. HMAC, session CAS, `confirm=true`, operation IDs, and the 64 KiB
  source limit do not constrain the code's behavior. Use only with trusted MCP
  clients and reviewed source.
- The in-ANSA bridge has no background socket worker or request queue. A GUI
  `BCTimer` invokes a fully non-blocking reactor every 25 ms, so socket accept,
  reads, parsing, authentication, allowlist dispatch, and writes all execute on
  the ANSA GUI thread. The reactor admits at most 32 active connections, applies
  both a 5-second idle timeout and a non-renewable 5-second accept-to-request
  deadline, caps requests/responses at 1 MiB/4 MiB, and uses per-tick event and
  time budgets.
- The external client also applies one monotonic absolute deadline to the whole
  connected handshake/request/response exchange; trickled hello or response
  bytes cannot renew it.
- The recurring timer is owned by the visible **ANSA MCP Bridge** control window.
  The script remains inside the blocking `BCShow` call while that window is open;
  closing it stops the timer and bridge and records `offline` status.
- Dedicated save/export tools constrain file output to configured
  `allowed_roots`; the external server additionally confines database saves to
  `ANSA_MCP_WORKSPACE`. **Arbitrary Python is not path-constrained.** The bridge
  accepts only a non-empty list of absolute root paths and fails closed on
  malformed values.
- Model-changing tools require `confirm=true`. Save/create/update operations
  also require a caller-generated `operation_id` for idempotency and the live
  `session_nonce` plus expected database identity. Entity updates additionally
  require expected old values to reject stale writes.
- FastMCP performs strict JSON-type validation before a tool runs, and the bridge
  validates again. Numeric/string lookalikes such as `confirm=1` or
  `confirm="true"` are rejected rather than coerced.
- The installer never creates or overwrites `ANSA_TRANSL.py`, and never starts,
  stops, restarts, or attaches to ANSA. The user loads the bridge manually in the
  intended session.

These controls reduce accidental and remote misuse, but they are not an OS
sandbox and do not establish engineering correctness.

## Requirements

- Windows with a locally licensed ANSA installation.
- Python 3.10 or newer for the external MCP server. This Python is separate from
  ANSA's embedded Python runtime.
- Codex or another MCP client that supports stdio servers.
- Permission to load a Python script into the intended ANSA session.

Do not attempt to import ANSA's embedded `ansa` package in the external virtual
environment. Live-GUI ANSA API calls belong to the in-process bridge; the fixed
cantilever exercise uses ANSA's separate, documented batch Python mode.

## 1. Install the external MCP server

From this directory:

```powershell
uv sync --extra dev
```

This creates `.venv` from the checked-in lock file. If `uv` is unavailable,
create a Python 3.10+ virtual environment with your installed Python launcher
and run `.\.venv\Scripts\python.exe -m pip install -e ".[dev]"`.

Choose a writable, dedicated workspace:

```powershell
$env:ANSA_MCP_WORKSPACE = Join-Path `
  ([Environment]::GetFolderPath('MyDocuments')) 'ANSAMCP\workspace'
$env:PYTHONUTF8 = '1'
```

Optional installation hints improve discovery but do not launch ANSA:

```powershell
$env:ANSA_HOME = '<ANSA_INSTALL_ROOT>'
$env:ANSA_EXECUTABLE = '<FULL_PATH_TO_ANSA_LAUNCHER>'
```

Run the read-only environment probe:

```powershell
.\.venv\Scripts\python.exe .\probe_environment.py
```

Installation, documentation, or launcher detection does not prove that a live
session is reachable.

## 2. Install the in-ANSA bridge files

Select a user-owned script directory. The destination is mandatory so the
installer never guesses which ANSA installation or startup directory to edit.

```powershell
$pluginDirectory = Join-Path `
  ([Environment]::GetFolderPath('MyDocuments')) 'ANSAMCP\ansa_plugin'

.\install_ansa_bridge.ps1 `
  -Destination $pluginDirectory `
  -Workspace $env:ANSA_MCP_WORKSPACE
```

The installer:

1. copies the contents of [`ansa_plugin`](ansa_plugin) to the selected directory;
2. creates `%LOCALAPPDATA%\ANSAMCP\bridge.json` with a random token and port
   `48762`;
3. creates the allowed workspace if needed; and
4. prints the exact `start_ansa_mcp.py` path to load.

It also writes a token-free `bridge_config_path.txt` beside the installed
script. The ANSA loader uses that absolute path for the in-process bridge,
so ANSA and a packaged Codex host share the same config even if their
`LOCALAPPDATA` values differ. Reinstalling preserves a valid existing token;
do not copy or disclose the token itself.

It does not edit ANSA startup hooks. In particular, an existing
`ANSA_TRANSL.py` is left untouched. The installer supports Windows PowerShell
5.1 as well as PowerShell 7.

## 3. Load the bridge in the intended ANSA session

Open the intended ANSA GUI yourself. Using ANSA's normal script-loading
facility, manually execute the installed `start_ansa_mcp.py`. This explicit step
prevents the installer from injecting the bridge into every ANSA session.

ANSA opens a small **ANSA MCP Bridge** control window. Keep that window open for
as long as MCP access is required. `BCShow` intentionally keeps the Load Script
invocation active so ANSA's GUI event loop can drive the recurring `BCTimer`.
Closing the control window is the normal local stop action: it stops the timer,
closes the listener and active sockets, writes `offline`, and lets the loaded
script return.

### Recommended: persistent Plugins-ribbon entry (v0.5.0)

Build the native `.bpkg` with `build_ansa_plugin_package.py` for the installed
bridge. Install it through **Development > BETA Packager Installer > Installer**,
choose **Your .BETA plugins directory**, then restart ANSA. The buttons appear
under **Plugins > ANSA MCP**. See [plugin installation](plugin/README.md).
The entry loads automatically; Start launches the bridge service.

```powershell
.\.venv\Scripts\python.exe .\build_ansa_plugin_package.py `
  --output '.\dist\ANSA_MCP_Bridge-0.5.0-build' `
  --ansa-launcher '<ANSA_INSTALL_ROOT>\ansa64.bat'
```

Replace `<ANSA_INSTALL_ROOT>` with your ANSA installation directory. Omitting
`--bridge-entry` builds a portable package; use `ANSA_MCP_BRIDGE_CONFIG` to point
both processes to the same existing configuration. Building does not install
into the user's ANSA profile. Version 0.5.0 retains
the descriptor lifetime fix and bundles the dashboard runtime. Official install,
fresh-process Start, authenticated calls, model deltas and native GUI callbacks
passed in an isolated ANSA v25.1.2 profile. Confirm the actual desktop installation
after restarting ANSA.

### Alternative: Start/Status/Stop buttons without Plugin Manager

In ANSA use **Development > Load Script** to load the installed
`ansa_mcp_controls.py`. Loading it only registers three user-script buttons;
it does not start the bridge or modify the current model. Find the buttons in
**Custom > Scripts**, group **ANSA MCP**. **Start** opens the bridge status
window, with a requested tab position beside **Database**. Keep that window
open while using MCP; closing it stops the bridge. **Status** prints the current
state, and **Stop** closes the bridge. After an intentional restart, refresh the
authenticated session status and nonce before any model-changing call.

After updating `ansa_mcp_controls.py`, select that script in **Development >
Script Manager** and use **Reload** before pressing a button; previously
registered callbacks do not update when only the file on disk changes. If the
loaded copy is uncertain, save the model, restart ANSA, and use **Load Script**
to load the copy in the installed directory.

The old standalone descriptor caused an access violation at
`python311.dll+0x1525AD` and remains disabled. Do not reinstall the files under
`output/plugin_candidate`. It passed a temporary metadata object to
`session.setPluginInfos`, which was measured not to increase its reference count;
directly loading the former bridge entry also triggered an ANSA future-import
compile error. The v0.2.0 package addresses both compatibility problems.
The old machine-specific candidate removal helper is not distributed here;
use the official installer for the new package. The `.ppl.disabled` source is
retained only for regression tests, never for installation.

Then run:

```powershell
.\.venv\Scripts\python.exe .\probe_live_bridge.py
```

A successful result must contain `"connected": true` plus live `ping`,
capability, and session responses. A config file, a listening TCP port, or a
persisted status file by itself is not proof that the intended ANSA session is
connected.

If the control window says `online` but the probe reports `server
authentication failed`, compare the installed `bridge_config_path.txt` with
the MCP client's `ANSA_MCP_BRIDGE_CONFIG`. After updating installed files,
stop the old bridge and reload the script; a running bridge is not hot-reloaded.

## 4. Register the MCP server with Codex

Use the generated configuration and the same workspace:

```powershell
.\register_codex_mcp.ps1 `
  -PythonExe "$PWD\.venv\Scripts\python.exe" `
  -Workspace $env:ANSA_MCP_WORKSPACE
```

The script validates the bridge config and target Python import before changing
Codex. It refuses to replace an existing `ansa` entry unless `-Force` is
supplied; a forced replacement restores the previous Codex configuration if a
later step fails. It persists `cwd`, `startup_timeout_sec=30`, and
`tool_timeout_sec=180`, intentionally exceeding the bridge's default 125-second
client wait. Use `-Force` only when replacing the current same-name entry is
intended.

Alternatively, adapt
[`examples/codex_config.example.toml`](examples/codex_config.example.toml) to
your machine. Verify registration:

```powershell
codex.cmd mcp get ansa
```

After restarting the MCP client, call `get_environment` and
`get_live_bridge_status` before relying on the live session.

## Tools

The first 18 tools below are the production default. Examples require
`ANSA_MCP_ENABLE_EXAMPLES=1` in both the MCP and ANSA processes before startup.

| Tool | Effect | Important guard |
|---|---|---|
| `get_environment` | Reports installation, workspace, and bridge state | Detection is diagnostic only |
| `get_live_bridge_status` | Authenticated ping of the current bridge | Connectivity only |
| `get_live_capabilities` | Returns the loaded bridge's exact allowlist | Use before planning work |
| `get_live_session_info` | Returns ANSA/runtime, deck, and database identity | Read before writes |
| `get_live_model_summary` | Counts requested current-deck entity types | Read-only |
| `list_live_entities` | Returns a bounded, paged entity list | Exact entity type; bounded limit |
| `get_live_entity` | Reads one entity and selected card fields | Exact type and ID |
| `run_live_model_checks` | Executes allowlisted ANSA `Check` operations | Existing check history is retained, but current check results/ANSA-side state may be updated; results need engineering review |
| `save_live_database` | Writes a silent `.ansa` snapshot inside the workspace without changing the active database path/name | session/database CAS + `operation_id` + `confirm=true`; `overwrite=false` by default |
| `create_live_entity` | Creates one explicitly named current-deck entity | bounded scalar fields + session/database CAS + `operation_id` + `confirm=true` + card-value readback evidence |
| `set_live_entity_card_values` | Updates bounded card fields | session/database/value CAS + `operation_id` + `confirm=true` |
| `refresh_live_view` | Redraws the model view | `confirm=true` |
| `get_live_step_history` | Reads recent mutating steps, outcomes, and redraw results | Read-only, session-local; at most 100 steps |
| `execute_live_ansa_python_step` | Runs arbitrary Python on the current ANSA GUI thread, then redraws and records the step | **Not sandboxed/local code execution**; live nonce/database/deck, operation ID, `confirm=true`; source ≤64 KiB |
| `search_live_ansa_api` | Search the connected version's public API symbols | Read-only, paginated |
| `get_live_ansa_api_help` | Read runtime API signature/docstring | Does not execute the API |
| `get_live_entity_fields` | Discover existing entity card fields | Exact type and ID |
| `execute_live_ansa_operation` | Eight generic operations, version-probed | Session/database/deck checks, operation ID, confirmation |

### Optional teaching tools (not registered by default)

| Tool | Purpose | Constraint |
| --- | --- | --- |
| `prepare_cantilever_static_demo` | Imports a fixed 3D mesh into a separate ANSA batch session, validates counts, saves `.ansa`, and exports an Abaqus deck | `confirm=true`; new workspace run folder |
| `solve_cantilever_static_demo` | Runs installed Abaqus/Standard on that ANSA-exported deck | exact `run_id`; `confirm=true`; one submission per run |
| `inspect_cantilever_static_demo` | Reads the ODB and checks displacement and reaction balance | exact `run_id`; successful `.sta` required |
| `stage_visible_cantilever_static_demo` | Stage the fixed deck for the live GUI workflow | updated online bridge; shared workspace |
| `import_visible_cantilever_static_demo` | Import and redraw in an empty ANSA GUI model | fixed hash, session/database CAS, operation ID, confirmation |
| `export_visible_cantilever_static_demo` | Snapshot/export from the same GUI model | same run and bridge session; no overwrite |
| `solve_visible_cantilever_static_demo` | Solve the GUI-exported deck with Abaqus/Standard | input model stays visible; bridge shows stage text |
| `inspect_visible_cantilever_static_demo` | Check the ODB and reaction balance | solver proof and engineering review remain separate |

### Step-by-step GUI operation for arbitrary tasks

1. Load the updated bridge in the target ANSA GUI, keep its control window open,
   and verify an authenticated live connection with `get_live_bridge_status`.
2. Read the current `database`, `session_nonce`, and `deck` with
   `get_live_session_info`. Give each typed mutation or Python step a fresh
   `operation_id`; Python steps also need a short `step_name`, reviewed `code`,
   and `confirm=true`.
3. Keep each call small enough to observe and read back. On return, inspect
   `live_step.sequence`, `status`, and `view_refresh`; the control window shows
   the latest step. Query the model/entities/checks to verify the intended
   change before the next step.
4. A failed redraw response does not prove the model is visible. An
   `OUTCOME_UNKNOWN` requires state inspection, not retrying with a new ID.

`execution_returned=true` for arbitrary Python means only that the script
returned; `model_effect_verified=false` means its engineering effects are not
automatically checked. The GUI gets a redraw opportunity **after each MCP
call**, not after each internal Python statement or during a blocking ANSA API
call. External solvers and META still need their own integration and evidence.

### Fixed cantilever exercise

The demo is a 200 × 20 × 10 mm steel solid cantilever with 615 nodes and 320
C3D8I hexahedral elements, E = 210000 MPa, Poisson ratio 0.3, x=0 fixed, and
100 N downward distributed across the x=200 face. Units are mm, N, MPa. It
uses ANSA v25.1.2 batch import/save/export and an installed Abaqus/Standard
solver; it does not alter the open ANSA GUI database and does not require the
GUI bridge to be online. ANSA's imported entity counts and exported keywords
must pass before solver submission. Solver success requires the `.sta` success
marker and ODB, and ODB inspection checks the 100 N reaction balance.

To call all three tools through stdio MCP, from this project directory run:

```powershell
.\.venv\Scripts\python.exe .\examples\run_cantilever_demo.py
```

Set `ANSA_MCP_WORKSPACE` to a dedicated writable directory if desired. Each
run creates a unique `cantilever_demo/<run_id>` directory containing source and
ANSA-exported `.inp`, the `.ansa` database, ANSA/Abaqus logs, `.sta`, `.odb`,
`results.json`, and `verification.json`. The script prints the `run_id` after
preparation. If an interrupted run has already solved, inspect it without
submitting another job:

```powershell
.\.venv\Scripts\python.exe .\examples\run_cantilever_demo.py --inspect <run_id>
```

The Euler-Bernoulli tip deflection reference is 0.7619 mm. This reference and
the reaction check are useful sanity checks, not engineering qualification;
review the mesh, material, boundary conditions, solver messages, stress field,
and mesh sensitivity for any real design decision.

#### Visible fixed cantilever in the ANSA GUI

Open a **new empty ANSA model**, load the **updated** `start_ansa_mcp.py`, and
keep the bridge control window open. The live workflow refuses a model with
existing nodes, elements, materials, properties, or geometry; it never clears
or overwrites a user's model. `ANSA_MCP_WORKSPACE` must be within the bridge's
`allowed_roots`. First run `probe_live_bridge.py` and confirm the authenticated
ANSA PID/session nonce and `import_fixed_cantilever` in the capabilities.

Then run the staged stdio MCP client:

```powershell
$env:ANSA_MCP_WORKSPACE = Join-Path `
  ([Environment]::GetFolderPath('MyDocuments')) 'ANSAMCP\workspace'
.\.venv\Scripts\python.exe .\examples\run_visible_cantilever_demo.py
```

The imported mesh is fitted and redrawn in the current ANSA window. The
external Abaqus solve leaves that input model visible and updates stage text in
the bridge control window. A successful redraw return is not screenshot proof
or a continuous frame-by-frame animation. Do not retry an uncertain mutation
with a new operation ID; inspect the live model and files first. This visible
end-to-end example is implemented only for the fixed cantilever. Other
simulations can use the general Python step, but still need task-specific
modelling, solver, result, and engineering checks.

`get_live_capabilities` returns the exact bridge methods, model checks, default
summary types, limits, and entity/card validation policy. Entity types and card
fields are then validated by the active ANSA deck at call time; they are not a
static cross-deck allowlist. The arbitrary Python step can call the wider ANSA
API, but validity for the current version/deck still requires actual testing.
Write `operation_id` values must be 8-128 characters using letters, digits,
`_`, `.`, `:`, or `-`. Reuse the same ID when resolving an uncertain retry; do
not hide an unknown outcome by inventing a new ID. Before an ANSA mutation is
started, the bridge reserves the ID as `pending`; it changes that record to
`success` after typed-operation readback or after arbitrary Python returns
normally (the latter does **not** verify model semantics). A
successful same-ID/same-parameter retry returns the recorded result. Replaying a
`pending` ID returns `OUTCOME_UNKNOWN` without performing another mutation, and
reusing an ID with different parameters is rejected. The session-local ledger
retains at most 256 pending or successful records; when full, it rejects a new
write before mutation and never evicts an earlier safety record.

The external client's bridge-call timeout must be strictly greater than the
bridge configuration's `request_timeout_seconds` (with additional margin for
response transfer). A shorter client timeout can make the caller stop waiting
while ANSA is still executing. If a write may have started and its verified
response is not observed, the external client raises `OUTCOME_UNKNOWN`: inspect
the live state and, if a retry is appropriate, reuse the original
`operation_id`; never retry with a new ID. The abandoned call cannot receive a
later response, but a same-ID retry can receive the bridge's `OUTCOME_UNKNOWN`
response when the in-session ledger still records that operation as `pending`.

`run_live_model_checks` executes ANSA's allowlisted `Check` API. It preserves
the existing check history, but may update current check results and related
ANSA/UI state, so it is a diagnostic operation with state effects rather than
a purely read-only call.

## Recommended workflow

1. Call `get_environment`.
2. Require `get_live_bridge_status.connected == true`.
3. Read `get_live_capabilities` and `get_live_session_info`; retain the returned
   `session_nonce` and database identity.
4. Inspect the model using summaries and exact entity reads.
5. Run applicable model checks and retain their machine-readable output. Treat
   this as an ANSA check/state operation: it preserves existing check history
   but may update current check results.
6. Before a write, re-read the database and target entity.
7. Supply the returned session nonce, database identity, and (for updates) old
   field values; create a unique `operation_id`, then explicitly approve the
   write with `confirm=true`.
8. Re-read the changed entity and rerun relevant checks.
9. Save only to a new workspace-relative `.ansa` snapshot path and independently
   review it. The bridge uses silent `SaveAs`, so a successful snapshot preserves
   the active database name/path. Existing targets are rejected unless the user
   deliberately supplies `overwrite=true`.

## Why official IAP / `-listenport` is not the default backend

ANSA ships a Remote Control/IAP client and can be started with a listening port.
That interface is useful for trusted automation, but its script execution model
can accept arbitrary Python text or files and does not provide this project's
challenge-bound HMAC authentication plus fine-grained method allowlist. A process is attachable
only if ANSA was started (or restarted) with `-listenport <port>`, and careless
client defaults can reset a database or shut down listening. Any future IAP
backend must therefore put a loopback authentication/authorization gateway in
front of IAP rather than exposing raw script execution directly.

For those reasons this project detects the official client only as diagnostic
information and reports `official_iap_enabled=false`. The local, authenticated,
typed bridge is the default. Do not replace it with raw remote script execution
without a separate threat review and explicit user authorization.

## Validation

Offline checks:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe .\stdio_smoke.py
```

`pytest` and `stdio_smoke.py` validate Python logic, schemas, and the MCP stdio
handshake. They do **not** start ANSA, consume a license, exercise the embedded
API, prove bridge reachability, verify a model check, or validate any mesh or
solver deck.

Live connectivity requires all of the following in the same run:

1. the intended ANSA GUI session is open;
2. the installed bridge script is loaded in that session and its **ANSA MCP
   Bridge** control window remains open;
3. `probe_live_bridge.py` succeeds with authenticated live responses; and
4. MCP live tools return matching session/database information.

Engineering validation additionally requires model-specific geometry, mesh,
property, connection, load/constraint, solver-card, and solver-result review by
a qualified CAE engineer. This MCP cannot independently certify engineering
fitness.

The bridge keeps a visible **ANSA MCP Bridge** control window inside a blocking
`BCShow` call and runs a socket reactor from that window's GUI `BCTimer` every
25 ms. The listener and every accepted socket are non-blocking; accepting,
reading, parsing, authentication, allowlist dispatch, response serialization,
and writing all occur on the ANSA GUI thread. The reactor limits active
connections to 32, closes connections after 5 seconds of idle time or after the
non-renewable 5-second accept-to-request deadline, caps requests/responses at
1 MiB/4 MiB, and observes per-tick event and time budgets
(at most four completed requests or roughly 10 ms of dispatch work). Closing the
control window or invoking `stop` first stops the timer, then closes the listener
and active sockets, writes `offline`, and lets `BCShow` return.

This visible lifetime is required by the ANSA v25.1.2 GUITK contract. Its
`BCWindowCreate` reference explicitly says that `BCOnExitHide` has no preserving
effect when a script ends: the window is destroyed as if `BCOnExitDestroy` had
been used. The official timer examples parent `BCTimer` to a window and keep the
script in `BCShow`. A never-shown hidden window therefore cannot be used as a
persistent host after Load Script returns. `BCTimerSingleShot` is useful for
deferred callback work, but ANSA does not document self-rescheduling single-shot
callbacks as a way to survive script return, so this bridge does not rely on it.
Calling `BCShow` and then hiding the window is not equivalent: once the show call
returns, the script can end and the same destruction rule applies.

These transport bounds preserve ANSA's main-thread requirement, but they cannot
make a synchronous ANSA C/API call non-blocking. Large entity collections,
checks, and saves may still freeze the GUI until ANSA returns. If the client
times out after a write may have started, it must treat the result as
`OUTCOME_UNKNOWN`; the original disconnected call cannot receive a later
response. Inspect live state and reuse the same `operation_id` when appropriate;
the bridge will replay a verified success or return `OUTCOME_UNKNOWN` for a
still-pending record without applying the mutation again. Do not invent a new ID.

## Troubleshooting

- **`bridge config not found`** — run `install_ansa_bridge.ps1`, or set
  `ANSA_MCP_BRIDGE_CONFIG` to the generated file.
- **Connection refused** — the bridge was not loaded, its control window was
  closed, it was loaded in another session, exited, or is using a different
  config/port. Do not treat it as a reason to restart or kill ANSA automatically.
- **`status.json` says running but the probe fails** — the file is diagnostic
  history and may be stale. Trust only a current authenticated probe/`ping`;
  reload or stop the bridge only after checking the intended ANSA session.
- **Authentication failed** — ensure the external server and in-ANSA bridge read
  the same config path. The installed `bridge_config_path.txt` pins ANSA to it;
  rerunning the installer against that exact config preserves its valid token.
- **Path rejected** — use a relative save path beneath `ANSA_MCP_WORKSPACE`; do
  not broaden `allowed_roots` merely to bypass the error.
- **Stale database/value error** — another action changed the session. Re-read
  session and entity state, then reconsider the intended change.
- **ANSA API/type/field rejected** — query capabilities and the live entity.
  Names differ by active deck and ANSA release; do not guess card fields.

## Development entry points

- `python -m ansa_mcp` — installed/venv stdio server entry point.
- `python server.py` — source-checkout convenience entry point.
- `probe_environment.py` — read-only configuration and path diagnostics.
- `probe_live_bridge.py` — authenticated, read-only live bridge probe.
- `stdio_smoke.py` — external MCP stdio smoke test; no live ANSA proof.
