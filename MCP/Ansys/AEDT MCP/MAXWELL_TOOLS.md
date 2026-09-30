# Maxwell 专用工具 / Dedicated Maxwell tools

本模块增加 15 个 `maxwell_*` 工具，AEDT MCP 总工具数为 45。基于项目固定的 PyAEDT 1.5.0；注册工具与离线测试不等于 Maxwell 实机求解验证。

This module adds 15 `maxwell_*` tools, bringing the AEDT MCP total to 45. The adapter targets the pinned PyAEDT 1.5.0 API. Registration and offline tests do not establish live Maxwell solve validity.

## 安装与加载 / Installation and loading

使用 [中文 README](README.zh-CN.md) 或 [English README](README.md) 的安装及 MCP 客户端配置。更新后重启 AEDT MCP 服务，并让客户端刷新工具清单；已运行的 MCP 服务不会自动注册新工具。无需在 AEDT 内安装插件。需要重启的是 MCP 服务，已有 AEDT 窗口可以保持打开。

Follow the installation and MCP client configuration in either README. Restart the AEDT MCP server and refresh the client's tool list after updating. A running server does not automatically register new tools. No in-AEDT plugin is needed; the existing AEDT window can remain open.

## 通用参数 / Common arguments

每个专用工具必须提供 `project_name`、`design_name`，以及 `pid` 或 `port` 中的一个。工程必须已打开，设计必须已存在且类型为 Maxwell 2D/3D。工具不会根据前台窗口猜测目标，也不会隐式创建缺失设计。先调用 `check_aedt_installed` 和 `check_aedt_status`，再连接明确会话。调用完成后使用 `release_connection` 保留 AEDT 窗口并释放 broker。

Each dedicated tool requires `project_name`, `design_name`, and exactly one of `pid` or `port`. The project must already be open and the existing design must be Maxwell 2D/3D. Tools do not infer a foreground target or implicitly create missing designs. Check installation/status, then connect to an explicit session. Use `release_connection` afterwards to retain the AEDT window and release the broker.

## 工具清单 / Tool list

| Tool | 中文用途 | Purpose |
|---|---|---|
| `maxwell_assign_coil` | 对已有截面/端子分配线圈，设置导体数和极性 | Assign a coil terminal, conductor count and polarity |
| `maxwell_assign_winding` | 创建 Current/Voltage/External 绕组组，设置实心/绞线、电流、电压、R/L、相位和并联支路 | Create a winding group and electrical properties |
| `maxwell_add_winding_coils` | 把已有线圈端子关联到指定绕组 | Link existing coils to a winding |
| `maxwell_assign_current` | 对已有对象或 3D 面分配直接电流激励 | Assign direct magnetic current excitation |
| `maxwell_assign_rotate_motion` | 对已有包围运动对象的 band 分配旋转运动 | Assign rotation to an existing enclosing band |
| `maxwell_assign_translate_motion` | 对已有 band 分配平移运动 | Assign translation to an existing enclosing band |
| `maxwell_assign_force` | 创建电磁力计算参数 | Create an electromagnetic force parameter |
| `maxwell_assign_torque` | 创建电磁转矩计算参数 | Create an electromagnetic torque parameter |
| `maxwell_set_eddy_effects` | 对导体设置涡流及相关位移电流选项 | Configure conductor eddy effects |
| `maxwell_create_setup` | 按当前求解类型的原生模板创建求解设置 | Create a setup using the current solver template |
| `maxwell_assign_length_mesh` | 创建局部长度网格操作 | Create local length mesh refinement |
| `maxwell_get_design_info` | 读取对象、单位、激励、运动、setup 和网格操作 | Read objects, units, boundaries, motion, setups and mesh operations |
| `maxwell_get_analysis_status` | 读取桌面求解活动和指定 setup 的数据可用性 | Read desktop activity and setup result availability |
| `maxwell_get_solution_data` | 按准确表达式名读取数值曲线、实虚部、单位和实际 variation | Read numerical curves, complex components, units and actual variation |
| `maxwell_create_field_plot` | 按明确 setup、时间/频率/相位创建表面或 3D 体场图 | Create surface or 3D volume field plots with explicit intrinsics |

## 线圈与绕组示例 / Coil and winding example

以下为 MCP 参数示例；`50051`、工程/设计名和对象名必须替换为实际目标。此流程只创建激励，不创建绕线几何。2D 使用对象名，3D 使用端子截面对象名或有效面 ID。`conductors_number` 是该端子的导体/匝数；`parallel_branches` 是绕组的并联支路数，两者含义不同。

These are MCP argument examples. Replace `50051`, project/design names and object names with your actual target. The tools assign excitations; they do not construct coil geometry. Use object names in 2D and terminal sheet names or valid face IDs in 3D. `conductors_number` and `parallel_branches` describe different quantities.

```json
{
  "tool": "maxwell_assign_coil",
  "arguments": {
    "port": 50051, "project_name": "Motor", "design_name": "Motor2D",
    "assignment": ["PhaseA_In"], "name": "CoilA_In",
    "conductors_number": 20, "polarity": "Positive"
  }
}
```

对另一端子使用 `polarity="Negative"`，然后创建绕组并关联两端子。

Assign the opposite terminal with `polarity="Negative"`, then create a winding and link both terminals.

```json
{
  "tool": "maxwell_assign_winding",
  "arguments": {
    "port": 50051, "project_name": "Motor", "design_name": "Motor2D",
    "name": "PhaseA", "winding_type": "Current", "is_solid": false,
    "current": "2A*sin(2*pi*50*time)", "parallel_branches": 1
  }
}
```

```json
{
  "tool": "maxwell_add_winding_coils",
  "arguments": {
    "port": 50051, "project_name": "Motor", "design_name": "Motor2D",
    "winding_name": "PhaseA", "coils": ["CoilA_In", "CoilA_Out"]
  }
}
```

电流表达式必须在目标 AEDT 设计中有效，示例表达式也需要与所选求解器核对。External 绕组只创建绕组定义，外部电路及其耦合仍需另外配置。

Current expressions must be valid in the selected AEDT design/solver. An External winding defines the winding only; external circuitry and coupling must be configured separately.

## 运动和求解示例 / Motion and solve example

运动工具要求磁瞬态设计，按 PyAEDT 1.5.0 读回的标准类型为 `Transient`。`RotorBand` 必须事先创建且包围全部运动对象；工具不会自动生成 band 几何，也不会证明拓扑、气隙或运动包围关系正确。

Motion tools require a magnetic transient design with PyAEDT's normalized `Transient` solution type. Create `RotorBand` first and ensure it encloses all moving objects. The tools neither construct band geometry nor verify topology, air gaps or containment.

```json
{
  "tool": "maxwell_assign_rotate_motion",
  "arguments": {
    "port": 50051, "project_name": "Motor", "design_name": "Motor2D",
    "band_object": "RotorBand", "angular_velocity": "1000rpm",
    "axis": "Z", "has_rotation_limits": false
  }
}
```

```json
{
  "tool": "maxwell_create_setup",
  "arguments": {
    "port": 50051, "project_name": "Motor", "design_name": "Motor2D",
    "name": "TransientSetup", "properties": {"StopTime": "20ms", "TimeStep": "0.1ms"}
  }
}
```

`properties` 使用当前求解器的原生 setup 属性。未知顶层属性会被拒绝，避免拼写错误被静默忽略。使用 `maxwell_get_design_info` 读回设置，然后调用现有 `validate_design` 和 `analyze_design`。数值量、单位、步长和收敛目标仍需按物理问题复核。

Use native setup property names for the selected solver. Unknown top-level names are rejected to prevent silently ignored typos. Read back settings with `maxwell_get_design_info`, then use the existing `validate_design` and `analyze_design`. Review units, time steps and convergence criteria for the actual physical problem.

## 结果和证据 / Results and evidence

- `api_accepted` 只表示 PyAEDT 返回了对应对象/成功值；`api_properties` 是 PyAEDT 的属性快照，不能作为独立原生读回证据。`native_properties` 和 `readback_confirmed` 记录实际原生属性访问结果；读回不可用时会明确给出错误或未确认状态。
- 绕组关联是原生 void 操作；工具额外读取原生绕组节点的子名称。只有确认请求的线圈端子出现在该绕组下，才返回 `association_confirmed=true`。读回不可用或不匹配时保持 false，必须在 AEDT 中复核端子归属。
- 运动工具返回 `geometry_enclosure_verified=false`；涡流工具可读回每个导体的 `GetEddyEffect`，位移电流选项仍返回未独立确认。
- `maxwell_get_analysis_status` 的 running 状态作用于整个指定 AEDT 桌面。已有数据可能来自以前的求解；桌面空闲、`is_solved` 或数值曲线均不能独立证明最新求解完成，因此 `solver_completion_confirmed` 保持 false。
- 数值结果返回实际 `active_variation`、可用 variation、横轴/结果单位及显式截断标志。默认只返回当前 active variation 的曲线；多工况需要分别请求。表达式必须使用目标 AEDT 报告中的准确名称。
- 2D 场图使用 `surface`，3D 可使用 `surface` 或 `volume`。`intrinsics` 可指定 `Time`、`Freq`、`Phase`。创建场图不等于场图已导出为图片，也不等于结果正确。

English:

- `api_accepted` records PyAEDT's return value; `api_properties` is its property snapshot, not independent native evidence. `native_properties` and `readback_confirmed` distinguish actual native access from cached data.
- Winding links use a native void API. The adapter additionally reads the winding's native child names and confirms membership only when all requested coils appear there. Missing or mismatched readback leaves `association_confirmed=false`; review terminals in AEDT.
- Motion containment and displacement-current settings remain explicitly unverified. Eddy effects are read back per conductor where supported.
- Running state is desktop-wide. Existing result availability can be stale and does not establish completion of the latest solve; `solver_completion_confirmed` remains false.
- Curves include the actual active variation, available variations, units and truncation flags. One active variation is returned at a time. Use exact AEDT report expression names.
- 2D uses surface plots; 3D also supports volume plots. Creating a plot does not export an image or validate results.

## 验证 / Verification

离线测试覆盖注册、路由、PyAEDT 1.5.0 方法签名、错会话/工程/设计、2D 面选择、极性/匝数、非瞬态运动、重复名称、原生失败、读回不可用，以及空/错误结果。它们使用替身对象，不能证明真实求解正确。

Offline tests cover registration, dispatch, pinned API signatures, target/design guards, 2D selection, polarity/counts, motion physics, duplicate names, API failures, missing readback and invalid result data. They use fake applications and do not validate a real solve.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

可选实机脚本通过真正的 MCP stdio 客户端运行工具。在已有会话中创建唯一命名的测试工程，保存 `.aedt`、JSON 报告和日志，空闲时仅关闭测试工程并恢复原活动工程。`--solve` 另外运行小型 2D 静磁场算例；不求解旋转/平移模型，不能用其结果证明电机仿真已通过验证。脚本在连接前检查 PyAEDT 是否能发现指定会话；发现失败时停止，避免隐式启动新 AEDT。

The optional live script calls the actual MCP stdio server, creates a uniquely named test project in an existing session, and saves the project, JSON report and logs. When idle, it closes only the test project and restores the previous active project. `--solve` runs a separate small 2D magnetostatic case. Motion designs are assignment smoke tests, not solved motor benchmarks. A discovery preflight stops attachment if PyAEDT cannot identify the existing session.

```powershell
.\.venv\Scripts\python.exe scripts\verify_maxwell_tools.py `
  --port 50051 `
  --install-dir '<AEDT_INSTALL_DIR>' `
  --output-dir 'test-artifacts\maxwell-live' `
  --solve
```

可使用 `--pid <PID>` 替换 `--port`，两者不能同时提供。进程权限限制可能影响 PyAEDT 的会话发现，必须在能访问该桌面进程的正常用户环境中执行。

Use `--pid <PID>` instead of `--port` if appropriate, never both. Process-access restrictions may prevent PyAEDT discovery; run in an execution identity that can access the existing desktop process.

官方接口参考 / Official API references:

- [PyAEDT Maxwell3d](https://aedt.docs.pyansys.com/version/stable/API/_autosummary/ansys.aedt.core.maxwell.Maxwell3d.html)
- [PyAEDT Maxwell2d](https://aedt.docs.pyansys.com/version/stable/API/_autosummary/ansys.aedt.core.maxwell.Maxwell2d.html)
