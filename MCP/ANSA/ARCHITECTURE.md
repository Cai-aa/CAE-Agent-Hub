# ANSA MCP architecture and trust boundaries

## Goals

ANSA MCP gives an MCP client operations against the database already open in a
user-selected ANSA process. Its design priorities are:

1. preserve the user's authority over which ANSA session receives the bridge;
2. expose typed operations plus a separately explicit, high-risk arbitrary
   Python step for tasks not covered by typed operations;
3. distinguish installation discovery, MCP startup, bridge reachability, live
   database state, and engineering validity;
4. constrain file output and require confirmation plus stale-write checks for
   model changes; and
5. fail closed when configuration, authentication, protocol, or ANSA state is
   ambiguous.

The arbitrary Python step has the full authority of ANSA's embedded interpreter
and is effectively local code execution by the authenticated MCP caller. It is
not a sandbox, a license manager, or an engineering certifier.

## Components

```text
                         trust boundary A
 MCP client  <-------------------------------->  external Python process
             MCP JSON-RPC over stdio             src/ansa_mcp
                                                        |
                                                        | reads
                                                        v
                                          %LOCALAPPDATA%\ANSAMCP\bridge.json
                                                        |
                          trust boundary B              |
                                                        v
 external Python process  --------------------->  in-ANSA bridge
                          TCP 127.0.0.1:48762     ansa_plugin/
                          HMAC + JSON lines             |
                                                        | allowlisted calls
                                                        v
                                               current ANSA API/database
```

### External FastMCP process

The external process is launched by Codex or another MCP client using
`python -m ansa_mcp`. It can run in an ordinary CPython virtual environment and
must not import ANSA's embedded `ansa` module.

Responsibilities:

- publish fixed MCP tool schemas;
- discover installation/docs only for diagnostics;
- validate relative workspace paths;
- load and validate the bridge endpoint configuration;
- authenticate and correlate every bridge request;
- limit response size and timeouts; and
- translate bridge failures into explicit MCP errors.

### In-ANSA bridge

The user manually loads `ansa_plugin/start_ansa_mcp.py` in the intended ANSA
session. This makes session selection an explicit human action. The installer
does not edit `ANSA_TRANSL.py`, change ANSA startup configuration, or manage ANSA
processes. Loading the script opens a visible **ANSA MCP Bridge** control window;
the script remains inside that window's blocking `BCShow` call until the user
closes it or the bridge is stopped.

Responsibilities:

- reject non-loopback endpoint configuration;
- require `SO_EXCLUSIVEADDRUSE` on Windows and never enable Winsock
  `SO_REUSEADDR`, so the port cannot be shared after the bridge binds it;
- retain a visible **ANSA MCP Bridge** control window inside blocking `BCShow`,
  and drive the bridge with that window's GUI `BCTimer` every 25 ms;
- accept, read, parse, authenticate, dispatch, serialize, and write through a
  fully non-blocking socket reactor on the ANSA GUI thread;
- validate the wire version, challenge-bound HMAC proof, ID, method, and
  parameter object;
- dispatch only the fixed method allowlist;
- perform ANSA API calls in the bridge's controlled execution path;
- bound list sizes, fields, checks, and response size;
- enforce confirmation, database identity, expected-value, and allowed-root
  guards for typed side effects; arbitrary Python intentionally bypasses the
  allowed-root/file restrictions and requires code review; and
- return structured success or error envelopes without exposing tracebacks or
  secrets to the client.

### Shared configuration

Default path:

```text
%LOCALAPPDATA%\ANSAMCP\bridge.json
```

Override for both processes:

```text
ANSA_MCP_BRIDGE_CONFIG=<absolute path>
```

Schema:

```json
{
  "version": 1,
  "host": "127.0.0.1",
  "port": 48762,
  "token": "64-character-random-hex-value",
  "allowed_roots": ["C:\\Users\\user\\Documents\\ANSAMCP\\workspace"],
  "request_timeout_seconds": 120
}
```

The generated token is a local shared credential. It must not appear in logs,
wire messages, MCP tool output, screenshots, source control, or command-line arguments. The
installer reuses an existing token only when it is exactly 64 hexadecimal
characters, so routine updates do not silently break a loaded client/bridge pair.

The bridge may write `status.json` beside the configuration as bounded
diagnostic lifecycle history. That file is not authoritative liveness state and
may outlive or lag the in-process bridge. Only a current authenticated
`probe_live_bridge.py`/`ping` response establishes live reachability.

The diagnostic states are deliberately ordered. After the socket is bound and
the timer is started, the bridge writes `starting`. Only the first successful
timer callback on the ANSA main thread may advance it to `online`. Closing the
control window or invoking the stop path writes `offline`. Even an `online`
snapshot can become stale; live proof still requires an authenticated ping whose
process ID and callback thread identity match the intended ANSA session.

`allowed_roots` is a defense-in-depth boundary for dedicated bridge file tools,
not for arbitrary Python steps. The
external `save_live_database` tool independently resolves a relative path under
`ANSA_MCP_WORKSPACE` and rejects traversal. The two settings should point to the
same dedicated directory.

## Wire protocol

Wire protocol v3 uses one connection per request and one UTF-8 JSON object per
line. It is intentionally independent from the configuration schema version.
The client first sends a nonsensitive hello containing only a fresh nonce:

```json
{
  "version": 3,
  "type": "client_hello",
  "client_nonce": "64-lowercase-hex-characters"
}
```

The server binds that nonce and a fresh challenge into its authenticated hello:

```json
{
  "version": 3,
  "type": "server_hello",
  "client_nonce": "same-client-nonce",
  "challenge": "64-lowercase-hex-characters",
  "server_proof": "HMAC-SHA-256-hex"
}
```

Only after verifying `server_proof` does the client send:

```json
{
  "version": 3,
  "type": "request",
  "id": "client-generated-correlation-id",
  "method": "get_session_info",
  "params": {},
  "client_nonce": "same-client-nonce",
  "challenge": "same-64-lowercase-hex-characters",
  "client_proof": "HMAC-SHA-256-hex"
}
```

Success response:

```json
{
  "version": 3,
  "id": "client-generated-correlation-id",
  "ok": true,
  "result": {},
  "client_nonce": "same-client-nonce",
  "challenge": "same-64-lowercase-hex-characters",
  "server_proof": "HMAC-SHA-256-hex"
}
```

Failure response:

```json
{
  "version": 3,
  "id": "client-generated-correlation-id",
  "ok": false,
  "error": {
    "code": "PUBLIC_ERROR_CODE",
    "message": "bounded diagnostic message",
    "retryable": false
  },
  "client_nonce": "same-client-nonce",
  "challenge": "same-64-lowercase-hex-characters",
  "server_proof": "HMAC-SHA-256-hex"
}
```

Each proof covers both fresh nonces/challenges, a purpose-specific domain
separator, and deterministic JSON (`sort_keys=true`, compact separators, UTF-8,
and no NaN). The raw token is never sent. Because the client nonce is new for
each call, a recorded server hello cannot be replayed by a process that bound the
port first to solicit method/parameters. The client verifies the hello before
disclosing its request, then verifies the response proof and exact response ID
before accepting data. It rejects invalid JSON, caps each hello at 4 KiB and the
response at 4 MiB, and reports a closed connection as failure. One monotonic
absolute deadline covers the client's whole connected exchange, so trickled
hello or response bytes cannot extend it. The in-ANSA reactor caps a request at
1 MiB, a response at 4 MiB, and active connections at 32. It closes an idle
connection after 5 seconds and also enforces a non-renewable 5-second deadline
from accept to a complete request, so trickled bytes cannot retain a slot
indefinitely. A TCP accept or a status file alone is never upgraded to
`connected=true`; that state requires a current authenticated `ping` response.

## Operation layers

### Fixed batch simulation tools

`prepare_cantilever_static_demo`, `solve_cantilever_static_demo`, and
`inspect_cantilever_static_demo` form a separate, fixed workflow. They do not
use the live socket bridge or change the open GUI database. The external MCP
generates a deterministic 200 × 20 × 10 mm Abaqus deck in a fresh directory
under its workspace. ANSA's documented `-nogui -exec load_script:<fixed script>`
mode imports it, checks 615 nodes/320 hexahedra/materials, saves `.ansa`, and
exports an Abaqus deck. Only that ANSA-exported deck is submitted to the
installed Abaqus/Standard solver. The final tool requires the solver's `.sta`
success marker and reads the ODB for tip displacement, peak stress, and fixed
reaction balance. No MCP argument supplies Python, shell commands, solver
options, or arbitrary file paths. Each run uses a random 32-character ID and
new workspace directory; solver submission refuses an already-submitted run.

Batch ANSA and Abaqus are separate processes with separate license and failure
modes. Their logs, files, and return codes must be checked independently. The
Euler-Bernoulli comparison is a sanity reference, not a mesh-convergence or
engineering-validity claim.

### Fixed visible-GUI cantilever workflow

`stage_visible_cantilever_static_demo` creates only a deterministic source deck
under the shared workspace after a live bridge capability check. A separate
`import_visible_cantilever_static_demo` call validates its pinned SHA-256 inside
the authenticated in-ANSA bridge, requires matching session/database identity
and an empty model, then calls ANSA `InputAbaqus`, `ZoomAll`, and `RedrawAll` on
the GUI thread. `export_visible_cantilever_static_demo` requires the same run
in that bridge session, checks entity counts, and writes a non-overwriting
`.ansa` snapshot and Abaqus deck from the visible ANSA model. The existing
solver/result gates apply to the exported deck. The bridge control window
shows coarse workflow phases while the separate Abaqus/Standard process runs;
it does not show Abaqus iterations or replace META post-processing. Synchronous
ANSA API calls may briefly block GUI painting and are not a frame-by-frame
geometry animation. A successful API redraw does not itself prove what the
user saw; live visual verification remains a separate evidence step.

### Bridge protocol methods

The external tools map to bridge methods as follows:

| MCP tool | Bridge method |
|---|---|
| `get_live_bridge_status` | `ping` |
| `get_live_capabilities` | `get_capabilities` |
| `get_live_session_info` | `get_session_info` |
| `get_live_model_summary` | `get_model_summary` |
| `list_live_entities` | `list_entities` |
| `get_live_entity` | `get_entity` |
| `run_live_model_checks` | `run_model_checks` |
| `save_live_database` | `save_database` |
| `create_live_entity` | `create_entity` |
| `set_live_entity_card_values` | `set_entity_card_values` |
| `refresh_live_view` | `refresh_view` |
| `get_live_step_history` | `get_step_history` |
| `execute_live_ansa_python_step` | `execute_python_step` |
| `import_visible_cantilever_static_demo` | `import_fixed_cantilever` |
| `export_visible_cantilever_static_demo` | `export_fixed_cantilever` |
| visible solver/inspection phase updates | `set_fixed_cantilever_phase` |

`get_environment` is primarily an external diagnostic tool and augments its
report with an authenticated bridge status probe.

### Read path

Read tools still validate entity type, requested fields, pagination, and issue
limits. The active solver deck affects valid names and fields. A read failure is
reported rather than replaced with invented or cached model data.

`run_model_checks` is not a pure read operation. It executes the allowlisted
ANSA `Check` API with the `KEEP_OLD` history policy, so existing check history
is retained, but the current check results and related ANSA/UI state may be
updated. Its output is diagnostic evidence and still requires model-specific
engineering review.

### Write path

All model side effects require `confirm=true`. Additional rules include:

- `save_database`: target must resolve beneath the configured workspace and use
  an `.ansa` suffix. It performs a silent snapshot that preserves the active
  database name/path; existing targets require explicit `overwrite=true`;
- `save_database`, `create_entity`, `set_entity_card_values`, and
  `execute_python_step` require a
  caller-generated `operation_id` for idempotency, plus the live session nonce
  and database identity obtained from the current session;
- `create_entity`: values are restricted to bounded JSON scalars, and the
  created entity's requested card values are read back and compared before the
  result is considered verified; and
- `set_entity_card_values`: the caller supplies database identity plus expected
  old field values. The bridge compares them before changing anything;
- `execute_python_step`: requires an expected current deck and a maximum 64 KiB
  UTF-8 script. It executes unrestricted Python in ANSA's GUI process. These
  guards do not sandbox code or restrict files, subprocesses, or ANSA API calls.

These are compare-and-set (CAS) guards. They reduce stale-agent writes but do not
provide a multi-operation transaction or undo guarantee. The client must re-read
and re-check after every change.

An `operation_id` contains 8-128 characters from `A-Z`, `a-z`, `0-9`, `_`, `.`,
`:`, and `-`. Immediately before mutation, the bridge reserves it as `pending`;
typed-operation readback or a normal Python-script return transitions it to
`success`; normal script return does not verify its engineering effects. A
same-method/same-parameter replay of `success` returns the recorded result. A
replay of `pending` returns `OUTCOME_UNKNOWN` without running the mutation
again, while cross-method or changed-parameter reuse is rejected. The
session-local ledger retains at most 256 pending or successful records in
memory. It never evicts them: a full ledger rejects the next write before
mutation with `PRECONDITION_FAILED`.

The external client also raises `OUTCOME_UNKNOWN` whenever it cannot prove a
durable-write response after a send may have occurred. The abandoned connection
cannot receive a later response; a same-ID retry can, however, receive the
bridge's `OUTCOME_UNKNOWN` response when that in-session record remains
`pending`. In either case, do not invent a new operation ID and retry blindly:
inspect live model/database state and reuse the original ID only when appropriate.

The external client's socket timeout must be strictly greater than the bridge
configuration's `request_timeout_seconds`, with additional margin for response
transfer. If the client timeout is shorter, the client may stop waiting while
the bridge is still executing; a started write then has an unknown outcome and
must follow the same state-inspection and original-ID rule.

### GUI step visibility

Every mutating bridge dispatch requests `base.RedrawAll()` on the ANSA GUI thread
after its handler returns, records a bounded event (sequence, method/label,
operation ID, status, redraw API result), and updates the visible bridge control
window. The last 100 events can be read with `get_live_step_history`; they are
session-local, not a durable audit log. Redraw failure is reported separately
from the mutation outcome so a committed write is not automatically retried.
One MCP call is one visible step boundary. Code inside a long Python call or a
blocking ANSA API cannot guarantee intermediate GUI frames. A redraw API return
does not prove what a person saw or that the model is valid.

## Main-thread execution and responsiveness

The bridge creates a visible **ANSA MCP Bridge** control window governed by
`BCOnExitDestroy`, starts its GUI `BCTimer`, and enters blocking `BCShow`.
While the control window remains open, the timer invokes the socket reactor every
25 ms. The listener and every accepted socket use `setblocking(False)`: accept,
read, JSON parsing, HMAC authentication, allowlist lookup, handler dispatch,
response serialization, and write all run in that timer callback on the ANSA GUI
thread. There is no TCP worker thread and no cross-thread request queue. The
bridge reports `starting` after bind/timer setup and reports `online` only after
the first successful callback verifies that it is running on the recorded ANSA
main thread.

The reactor bounds resource use to 32 active connections, a 5-second idle
timeout, a non-renewable 5-second accept-to-request deadline, 1 MiB requests,
and 4 MiB responses. Each tick also has event and time
budgets: at most four completed requests are dispatched, with roughly 10 ms
available for dispatch work. The `stop` path first stops the timer, then closes
the listener and every active socket, writes `offline`, and finally closes the
control window so `BCShow` and the Load Script invocation can return.

This lifetime is intentional, not a presentation choice. In the ANSA v25.1.2
GUITK reference, `BCWindowCreate` explicitly warns that `BCOnExitHide` has no
preserving effect when a script ends: the window is destroyed as if
`BCOnExitDestroy` had been selected. The official `BCTimer` examples parent the
timer to a window and keep the script in `BCShow`. Consequently, a never-shown
hidden parent cannot keep a child timer alive after Load Script returns. Calling
`BCShow` and then hiding the window only permits the show call and script to
return, so it does not create a persistent hidden host. `BCTimerSingleShot` is
documented for deferred callback execution, but not as a self-rescheduling
service that survives script return; the bridge does not rely on that
undocumented lifetime.

These bounds establish thread affinity and keep network I/O non-blocking; they
do not make ANSA calls asynchronous. Calls such as full-database
`CollectEntities`, checks, and `SaveAs` are synchronous and may freeze the GUI
until ANSA returns. Checks preserve existing check history but may update
current check results and ANSA/UI state. Once such a call has started, the bridge
cannot safely cancel it. If the client times out after a write may have started,
it must classify the result as `OUTCOME_UNKNOWN`, inspect state, and reuse the
same operation ID rather than assuming rollback or retrying with a new ID.

## Evidence states

The following states must not be collapsed:

```text
installation path found
        -> external MCP starts
        -> bridge config is valid
        -> authenticated bridge ping succeeds
        -> intended ANSA session identity matches
        -> requested API operation returns live data
        -> deterministic model checks pass
        -> CAE engineer accepts model/solver evidence
```

Passing an earlier state does not imply a later one. In particular:

- offline unit tests and `stdio_smoke.py` do not exercise ANSA;
- `status.json` is diagnostic history, not authoritative liveness;
- bridge reachability does not prove the intended database is open;
- a completed API call does not prove mesh, connection, load, or solver-card
  correctness; and
- model checks are necessary evidence, not an engineering sign-off.

## Official IAP policy

The installed ANSA distribution may include
`scripts\RemoteControl\ansa\AnsaProcessModule.py`, and ANSA can be launched with
`-listenport`. The external environment report detects this client but leaves
`official_iap_enabled=false`.

The official channel is not the default MCP backend because it supports sending
Python script text/files and does not provide this design's challenge-bound
bidirectional HMAC and typed fine-grained method allowlist. It also requires ANSA to have been
started (or restarted) with `-listenport <port>`. If used in a separately
authorized integration, a loopback authentication/authorization gateway must
stand in front of IAP, and pre-execution and post-connection lifecycle actions
must be chosen explicitly so an automation client does not reset the current
database or stop the listener.

The detection code does not connect through IAP and never launches ANSA with a
listener argument.

## Threat model and residual risks

### Addressed

- remote network exposure: loopback binding only;
- unauthenticated local calls and port-first impersonation without the
  credential: per-install credential plus challenge-bound bidirectional HMAC;
- generic code execution: fixed method dispatch and no raw script tool;
- arbitrary save paths: normalized workspace containment;
- accidental model changes: explicit confirmation;
- stale model writes: expected database and value checks;
- unbounded enumeration/response: page and response limits; and
- wrong-session auto-injection: manual bridge loading.

### Residual

- another process running as the same Windows user may be able to read the
  credential or repeatedly consume bounded loopback connection slots; the
  absolute deadline limits each unauthenticated slot but cannot eliminate local
  denial of service;
- ANSA Python APIs and valid card names differ by release and active deck;
- a sequence of individually guarded writes is not atomic;
- ANSA or plugin failure during a write can leave application-specific partial
  state unless ANSA itself makes that call atomic;
- the plugin is not an OS sandbox; and
- no software guard can replace model-specific CAE review.

## Lifecycle

1. User installs the external Python package.
2. User runs `install_ansa_bridge.ps1` with an explicit destination.
3. Installer copies project-owned bridge files and writes the shared config.
4. User opens/selects an ANSA session and manually loads
   `start_ansa_mcp.py`.
5. Bridge creates and shows its visible **ANSA MCP Bridge** control window,
   binds the configured non-blocking loopback listener, starts the 25 ms timer,
   writes diagnostic `starting`, and remains inside `BCShow`.
6. The first successful main-thread timer callback writes diagnostic `online`;
   the user then verifies with `probe_live_bridge.py` and matching process/thread
   identity.
7. MCP client launches the external server over stdio.
8. Tool calls read or change the current database under the guards above.
9. Closing the control window or explicit bridge `stop` stops the timer, closes
   all bridge sockets, writes diagnostic `offline`, and lets `BCShow` return.
   Closing ANSA also ends the in-process bridge. The external server remains
   unable to perform live operations until another intended session loads the
   bridge.

No installer or MCP tool is authorized to kill, restart, or silently relaunch
ANSA.
