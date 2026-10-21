# Adams publication validation

Tested on Windows with Python 3.11 and a user-owned Adams/View 2024.1 installation
on 2026-10-18. These are bounded bridge checks, not general mechanism validation.

| Check | Observed result |
| --- | --- |
| Unit and Windows subprocess regressions | 8 passed |
| MCP stdio initialize, list tools/resources, probe, create project | PASS; 16 tools, 3 resources |
| Installed native four-bar fixture | `VERIFIED`; process exit 0, model verified, no fatal signals, 51 numeric FY points |
| Public driven-box recipe | `VERIFIED`; process exit 0, model verified, no fatal signals, 101 numeric FY points |

The native fixture requests 5 seconds and 50 output steps; the public box recipe
requests 1 second and 100 output steps. Both exported the expected number of
samples (steps + initial sample). The source package does not include runtime
logs, installation paths, generated command files or vendor example source.

The live listener was unavailable during this validation, so live query and live
command integration are unverified. Direct Solver, plots and animation remain
unsupported. The configured release is an operator-provided value; discovery
labels are not an independent version or license certification. Time-completion
checks beyond scalar sample counts remain the operator's responsibility.

Reproduce the unit/protocol checks using the README commands. Reproduce native
checks by calling `adams_smoke_test` and the calls in
[examples/project_recipe.json](examples/project_recipe.json) with a fresh project
ID. Inspect the new run's `validation.json`, numeric export, request and logs.
