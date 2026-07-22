# HyperWorks 2026 advanced capability audit

This audit records what is actually exposed by the installed HyperWorks 2026 APIs and
what this MCP deliberately opens. Availability in `hmservices.py` is not treated as proof
that a workflow is safe for every solver profile.

## End-to-end analysis and postprocessing

MCP 0.8 includes the solver-specific OptiStruct SOL 101 profile covering MAT1/PSOLID/CHEXA,
FORCE, SPC1, optional PGAP/CGAP, subcase controls, H3D requests, asynchronous execution,
artifact classification, and in-application HyperView postprocessing. The regression
fixture was accepted by OptiStruct 2026 with 100 GRID entries, 40 CHEXA elements, one
CGAP element, and one PGAP card, and ended with `ANALYSIS COMPLETED` while producing H3D
and OP2 results. HyperView handling is allowlisted to workspace model/result files and a
PNG output; it returns the selected result metadata, legend minimum/maximum, bounded
entity query rows, and screenshot metadata.

MCP 0.8 also adds a bounded Radioss explicit block-impact profile. It generates paired
Starter and Engine decks with `/MAT/LAW2`, `/PROP/SOLID`, `/BRICK`, `/INIVEL/TRA`,
`/BCS`, `/INTER/TYPE7`, `/TH/PART`, `/TH/INTER`, `/ANIM/DT`, and `/H3D/DT`. The real
Radioss 2026 regression used 45 nodes and 12 HEXA8 solids. Starter ended with zero errors
and zero warnings; Engine ended normally and produced H3D, 11 `A###` frames, `T01`, OUT,
and restart artifacts. Parsed gates reported a positive 2.853e-4 ms minimum time step,
0% added-mass error, no negative-volume or penetration error marker, and 11.4% maximum
absolute energy error against the default 15% regression threshold. This threshold is a
fixture gate, not universal engineering acceptance criteria. HyperView now accepts an
explicit first/last/integer simulation selector and excludes non-finite contour rows from
reported extrema.

## Connection workflows

| Workflow | Installed API | MCP 0.6 state | Reason |
|---|---|---|---|
| Rigid link | `Model.rigidlink` | Verified and exposed | Real Radioss test created config 55 |
| RBE3 | `Model.rbe3` | Verified and exposed | Real Radioss test created config 56 and a centroid dependent node |
| Node weld | `Model.weld` | Verified and exposed | Real Radioss test created config 3 |
| Spot weld | `Model.createspotweld` | Audited, gated | FE config and property are solver-profile dependent |
| Generic connector realization | `CE_ConnectorCreateByList`, `CE_FE_RealizeWithDetails` | Audited, gated | Requires connector controls and solver-specific realization details |
| Fastener | `Model.fastenercreation` | Audited, gated | Installed API documentation limits this function to the Abaqus profile |

All exposed connection modifications create a workspace `.hm` checkpoint and verify new
element IDs. The real validation restored node/element counts after testing.

## HyperStudy and Design Explorer

The installation contains `hstbatch.exe`, `hstpy.bat`, the `alt.hst.api` Python package,
official API examples, and the in-application `designexplorer` module. MCP 0.6 exposes a
typed, project-scoped internal-math study generator:

- continuous variables with lower, nominal, and upper bounds;
- expression responses using a restricted expression character set;
- Hammersley, Full Factorial, or Modified Extensible Lattice Sequence DOE setup;
- GRSM minimize, maximize, and constraint goals;
- `.hstudy` generation through Altair `hstpy.bat`.

It does not accept arbitrary Python and does not automatically evaluate studies. A real
HyperStudy 2026 test created a 39,704-byte `.hstudy` containing two variables, one
response, a Hammersley DOE, and a validated GRSM optimization approach.

## Dummy, seatbelt, and airbag workflows

The generated API file contains exact signatures for dummy positioning/rotation, seatbelt
creation, and airbag create/update/review. In the live Radioss session, dummy and airbag
methods are callable, while `createseatbeltmesh`, `createseatbelt`, and
`create2dseatbeltwithmeshelementsize` are not present on the active `Model` object. The
installation also contains folding wrappers, but they use opaque `*args/**kwargs` and the
ribbon workflows depend on live `hwctx` selection state and options.

MCP 0.6 therefore exposes `get_live_safety_airbag_capabilities` as an audit-only tool.
Model-changing safety operations stay closed until representative solver-specific fixtures
are available:

1. a supported dummy collector with joint metadata and target points;
2. a seatbelt route with nodes, three planes, mesh settings, and valid output collectors;
3. a closed airbag shell model with initialized fold context;
4. ordered stitching edge paths and validated spring properties.

This boundary prevents a method being advertised merely because its name exists in the
binary wrapper.

---

## 中文摘要

- 已验证并开放：刚性连接、RBE3、节点焊接，全部带检查点和失败回滚。
- 已开放受控 HyperStudy 建模：连续变量、表达式响应、DOE、GRSM 目标和 `.hstudy` 生成；不会自动计算，也不接受任意 Python。
- 已审计但暂不开放：Spot Weld、通用 Connector Realization、Fastener、假人定位、安全带建模、气囊折叠和缝合；当前 Radioss 会话的 `Model` 对象没有开放安全带创建方法。
- 安全/气囊功能需要对应求解器的真实样例模型验证后，才会升级为可修改模型的 MCP 工具。
