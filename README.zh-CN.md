# CAE Agent Hub 使用教程

**语言：** [English](README.md) | 中文

CAE Agent Hub 是一个面向主流工程仿真软件的 MCP server、Agent Skill、求解器自动化脚本和浏览器结果查看器集合。目标是让 Codex、Cursor、Claude Code、Claude Desktop 等 AI 客户端连接真实 CAE 软件，而不是只生成离线示例。

当前仓库包含：

- Abaqus/CAE、ANSYS Fluent、ANSYS Workbench Mechanical、Ansys Electronics Desktop / HFSS 的 MCP server。
- 按工作流阶段组织的 Abaqus 有限元 skill。
- 原 Text to CAE 浏览器 viewer，用于查看导出的 `result_mesh.json` 仿真结果。
- 示例工作流和模板；求解器二进制文件、许可证、私有路径和生成结果不进入源码仓库。

## 仓库地址

```text
https://github.com/Cai-aa/CAE-Agent-Hub
```

部分示例目录仍保留旧名称 `text-to-cae`，用于兼容已有 viewer 案例。

## 架构

```text
AI client
  -> MCP server 或 skill instruction
  -> 正在运行的 CAE 应用或求解器脚本
  -> 原生求解结果
  -> 轻量 viewer 数据
  -> 浏览器检查或报告工作流
```

职责划分：

- **MCP servers**：给 AI 客户端提供真实 CAE 软件的 live tool access。
- **Skills**：提供可复用的建模、设置、求解、后处理和验证指令。
- **CAE applications**：执行真实求解。
- **Viewer modules**：在不打开求解器的情况下查看导出的结果数据。

## MCP Index

| MCP | 状态 | 用途 | 主要入口 | 触发关键词 |
| --- | --- | --- | --- | --- |
| [Abaqus MCP](MCP/Abaqus) | Active | 通过本地 TCP bridge 连接 live Abaqus/CAE；可在 Abaqus kernel 中运行 Python、检查模型、提交 job、监控状态、读取 ODB、截图 viewport。 | `mcp_server.py`, `abaqus_mcp_plugin.py`, `abaqus_plugins/mcp_control/` | Abaqus MCP, Abaqus/CAE, ODB, viewport, submit job |
| [ANSYS Fluent MCP](MCP/Ansys/Fluent%20MCP) | Active | 检测 Fluent、启动 batch journal、跟踪 job/log，并可管理 live PyFluent session 执行 Scheme、TUI 和 Python 探测。 | `server.py`, `tools/fluent_bridge.py`, `tools/pyfluent_session.py` | Fluent, PyFluent, journal, TUI, CFD |
| [ANSYS Workbench MCP](MCP/Ansys/Workbench%20MCP) | Active | 通过 Python helper 和 Mechanical ACT bridge 控制 Workbench / Mechanical，支持 file queue 和 socket timer 两种通信方式。 | `server.py`, `tools/`, `workbench_plugin/` | Workbench, Mechanical, ACT, LS-DYNA |
| [Ansys AEDT MCP](MCP/Ansys/AEDT%20MCP) | Active | 通过 raw TCP JSON bridge 连接 Ansys Electronics Desktop / HFSS；可查看工程、创建 HFSS design、保存工程、执行小段 AEDT Python。 | `mcp_server.py`, `aedt_mcp_bridge.py`, `scripts/install_aedt_toolkit_button.ps1` | AEDT, HFSS, Electronics Desktop, antenna |
| [Altair HyperWorks MCP](MCP/HyperWorks) | Active | 通过类型化、工作区隔离的工具和经过认证的应用内 Python bridge 控制 HyperWorks 与 live HyperMesh 会话；支持模型与实体检查、受控 batch Tcl 和求解任务管理。 | `src/hyperworks_mcp/server.py`, `hyperworks_extension/`, `install_hyperworks_extension.ps1` | HyperWorks, HyperMesh, HyperView, OptiStruct, Radioss, live Python bridge |
| [LAMMPS MCP](MCP/LAMMPS) | Active | 检测本地 LAMMPS、运行明确输入文件并保存作业证据。 | `server.py`, `tools/atomistic_bridge.py` | LAMMPS, 分子动力学, trajectory |
| [OVITO MCP](MCP/OVITO) | Active | 检测 OVITO 脚本能力、运行明确后处理脚本并保存证据日志。 | `server.py`, `tools/atomistic_bridge.py` | OVITO, 原子尺度, visualization |
| [CalculiX MCP](MCP/CalculiX) | Active | 包装开源有限元求解器 CalculiX（`ccx`，GPLv2，无需 license）：解析 `.inp`、原位修改设计变量、fire-and-forget 运行 ccx、读取 `.dat` 文本结果，并把 `.dat` 结果导出为 viewer 的 `result_mesh.json`，提取固有频率（`*FREQUENCY`）与可在 viewer 渲染的振型，并跑两阶段尺寸优化（LHS + 坐标下降），在应力/位移或频率约束（避共振）下最小化质量。 | `mcp_server.py`, `tools/inp_parser.py`, `tools/solver.py`, `tools/result_exporter.py`, `tools/optimizer.py` | CalculiX, FEM, ccx, .inp, .dat, .frd, von Mises, 设计变量, 尺寸优化, 模态分析, 共振 |
| [FEP Agent Hub](MCP/FEP-Agent-Hub) | Active | 通过三个独立、工作区隔离的 STDIO MCP 协同 FreeCAD 建模、Elmer FEM 网格/求解与 ParaView 后处理；包含 6 个经门禁验证的热、电磁、结构和层流 profile。 | `mcp/*/src/*_mcp/server.py`, `scripts/protocol_smoke.py`, `scripts/mcp_full_validation.py` | FreeCAD, Elmer FEM, ParaView, FEP, 热传导, 变压器, 简支梁, 层流, 楞次定律 |

> 新增 MCP 时，建议保留可复用源码、示例、测试和中英文 README；不要提交虚拟环境、求解结果、私有路径、许可证或生成的工程数据。

## Skill Index

| Skill | 状态 | 用途 | 触发关键词 |
| --- | --- | --- | --- |
| [abaqus](Skill/abaqus/core/abaqus) | Active | Abaqus FEA 脚本和分析工作流的总控路由 skill。 | Abaqus, FEA, finite element, simulation |
| [abaqus-geometry](Skill/abaqus/modeling/abaqus-geometry) | Active | 创建 part、sketch、extrusion、assembly，并导入 CAD。 | geometry, part, sketch, STEP, IGES |
| [abaqus-material](Skill/abaqus/modeling/abaqus-material) | Active | 定义材料、section、密度、弹性、塑性和常用工程材料参数。 | material, steel, aluminum, Young's modulus |
| [abaqus-mesh](Skill/abaqus/modeling/abaqus-mesh) | Active | 生成有限元网格并选择元素类型。 | mesh, elements, nodes, C3D8R |
| [abaqus-interaction](Skill/abaqus/modeling/abaqus-interaction) | Active | 定义接触、摩擦、tie、connector 和 bonded surface。 | contact, friction, tie, bonded |
| [abaqus-amplitude](Skill/abaqus/setup/abaqus-amplitude) | Active | 定义 ramp、pulse、cyclic、transient 等随时间变化的 amplitude。 | amplitude, ramp, pulse, cyclic |
| [abaqus-bc](Skill/abaqus/setup/abaqus-bc) | Active | 定义 fixed、pinned、clamped、displacement、symmetry 等边界条件。 | fixed, clamped, pinned, support |
| [abaqus-docs](Skill/abaqus/setup/abaqus-docs) | Active | 下载和管理 abqpy / Abaqus API 文档。 | Abaqus docs, API reference, abqpy |
| [abaqus-field](Skill/abaqus/setup/abaqus-field) | Active | 定义 initial condition 和 predefined field，例如初始温度、残余应力。 | initial condition, predefined field |
| [abaqus-load](Skill/abaqus/setup/abaqus-load) | Active | 施加集中力、压力、重力和分布载荷。 | force, pressure, gravity, load |
| [abaqus-output](Skill/abaqus/setup/abaqus-output) | Active | 配置 field output 和 history output 请求。 | output request, field output, history output |
| [abaqus-step](Skill/abaqus/setup/abaqus-step) | Active | 定义 analysis step、procedure、increment、time period 和 nlgeom 设置。 | step, static step, dynamic step, nlgeom |
| [abaqus-static-analysis](Skill/abaqus/analysis/abaqus-static-analysis) | Active | 静力结构分析完整工作流，用于应力、位移、反力、强度和刚度评估。 | static, stress, displacement, strength |
| [abaqus-modal-analysis](Skill/abaqus/analysis/abaqus-modal-analysis) | Active | 提取固有频率和振型，用于振动和共振检查。 | modal, frequency, vibration, resonance |
| [abaqus-dynamic-analysis](Skill/abaqus/analysis/abaqus-dynamic-analysis) | Active | 动力学完整工作流，用于 impact、crash、drop test、transient、显式/隐式动力学。 | impact, crash, drop test, explicit |
| [abaqus-thermal-analysis](Skill/abaqus/analysis/abaqus-thermal-analysis) | Active | 稳态或瞬态热传导分析工作流。 | thermal, heat transfer, conduction |
| [abaqus-coupled-analysis](Skill/abaqus/analysis/abaqus-coupled-analysis) | Active | 热-结构耦合分析，用于 thermal stress 和温度导致的变形。 | thermal stress, expansion, deformation |
| [abaqus-contact-analysis](Skill/abaqus/analysis/abaqus-contact-analysis) | Active | 多体接触分析，用于摩擦、过盈配合、螺栓和装配接触。 | contact analysis, friction, press fit |
| [abaqus-fatigue-analysis](Skill/abaqus/analysis/abaqus-fatigue-analysis) | Active | 疲劳和耐久性工作流，用于循环、损伤累计和寿命预测。 | fatigue, durability, cycles |
| [abaqus-job](Skill/abaqus/execution/abaqus-job) | Active | 创建、提交、监控和管理 Abaqus job 与 input file。 | submit job, input file, execute |
| [abaqus-export](Skill/abaqus/execution/abaqus-export) | Active | 导出 Abaqus 几何和结果到 STL、STEP、CSV、INP 或外部格式。 | export, STL, STEP, CSV, INP |
| [abaqus-odb](Skill/abaqus/postprocessing/abaqus-odb) | Active | 读取 ODB 结果并提取应力、位移、反力和结果摘要。 | ODB, maximum stress, displacement |
| [abaqus-optimization](Skill/abaqus/optimization/abaqus-optimization) | Active | 配置 Tosca optimization 的 response、objective、constraint 和 SIMP 类参数。 | optimization, objective, Tosca |
| [abaqus-shape-optimization](Skill/abaqus/optimization/abaqus-shape-optimization) | Active | 优化 fillet、notch 或 surface shape，降低峰值应力，不做拓扑删减。 | shape optimization, fillet, notch |
| [abaqus-topology-optimization](Skill/abaqus/optimization/abaqus-topology-optimization) | Active | 拓扑优化工作流，在保持刚度的同时减少质量。 | topology optimization, weight reduction |
| [fea-structural](Skill/abaqus/reference/fea-structural) | Reference | 通用结构有限元参考，覆盖静力、动力、非线性和验证。 | structural FEA, nonlinear, validation |
| [fenics-fem](Skill/abaqus/reference/fenics-fem) | Reference | FEniCS/dolfinx 有限元参考，用于弱形式、gmsh 网格、PDE 和 ParaView 导出。 | FEniCS, dolfinx, PDE, gmsh |
| [lammps-evidence-md](Skill/lammps/lammps-evidence-md) | Active | 证据优先的 LAMMPS 分子动力学工作流。 | LAMMPS, 分子动力学, stress-strain |
| [ovito-evidence-postprocessing](Skill/ovito/ovito-evidence-postprocessing) | Active | 证据优先的 OVITO 原子尺度后处理工作流。 | OVITO, visualization, atomistic |
| [ansys-mechanical-evidence-structural](Skill/Ansys/ansys-mechanical-evidence-structural) | Active | 与 Workbench 主工作流互补的 Mechanical 证据和验收门槛。 | Mechanical, ACT, PyMechanical, MAPDL |
| [aedt-evidence-electromagnetics](Skill/Ansys/aedt-evidence-electromagnetics) | Active | 含 Maxwell 检查的泛用 AEDT 证据工作流。 | AEDT, Maxwell, HFSS, PyAEDT |
| [comsol-motor-nvh-evidence](Skill/comsol/comsol-motor-nvh-evidence) | Active | 检查点式永磁电机 NVH 工作流，耦合旋转电磁、结构模态、声学与 Campbell 验证。 | COMSOL, 电机 NVH, Maxwell 力, 模态, Campbell |
| [calculix-fem](Skill/calculix/calculix-fem) | Active | 驱动 CalculiX MCP 的工作流：检视 `.inp`、原位修改设计变量、运行 ccx、读取 `.dat` 结果、导出 `result_mesh.json`。 | CalculiX, FEM, ccx, .inp, 线性静力 |
| [calculix-sizing-optimization](Skill/calculix/calculix-sizing-optimization) | Active | 在 CalculiX 壳/梁 deck 上跑两阶段尺寸优化（LHS 粗扫 + 坐标下降），在应力/位移约束下最小化质量；模态 deck 上可用固有频率下限约束（避共振）。 | CalculiX, 尺寸优化, 减重, LHS, 坐标下降, 共振, 固有频率 |
| [calculix-modal-analysis](Skill/calculix/calculix-modal-analysis) | Active | 从 CalculiX `*FREQUENCY` 步提取固有频率与振型；第 N 阶可导出为 viewer 的无应力振型。 | CalculiX, 模态, 固有频率, 振型, 共振, 振动 |
| [fep-agent-hub](Skill/fep-agent-hub) | Active | FreeCAD → Elmer FEM → ParaView 证据优先总控 Skill，覆盖已验证 profile、物理门禁、敏感性检查与真实动画口径。 | FEP Agent Hub, FreeCAD, Elmer FEM, ParaView, CAE 验证 |

> 新增 skill 时，请保留完整 skill 目录，包括 `SKILL.md`、可用的 `metadata.json`、上游来源、references、assets 和工作流脚本。

## 安装

### 克隆仓库

```powershell
git clone https://github.com/Cai-aa/CAE-Agent-Hub.git
Set-Location .\CAE-Agent-Hub
```

如果你之前克隆的是旧仓库名，GitHub redirect 通常仍然可用，但建议更新 remote：

```powershell
git remote set-url origin https://github.com/Cai-aa/CAE-Agent-Hub.git
```

### 使用 MCP server

每个 MCP 目录都有自己的 README 和环境变量模板。通用本地安装方式：

```powershell
Set-Location ".\MCP\<vendor>\<server folder>"
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -U pip
.\.venv\Scripts\python.exe -m pip install -e .
```

然后根据该 MCP 目录中的示例配置，把 server 注册到支持 MCP 的客户端。

### 使用 skills

Skill 是 instruction module，不是求解器二进制文件。请复制完整 skill 目录到 agent 的 skill 目录，或把相关 `SKILL.md` 作为项目上下文。

Codex 示例：

```powershell
New-Item -ItemType Directory -Force -Path "$env:USERPROFILE\.codex\skills" | Out-Null
Copy-Item -Recurse -Force ".\Skill\abaqus\analysis\abaqus-static-analysis" "$env:USERPROFILE\.codex\skills\abaqus-static-analysis"
```

示例提示词：

```text
Use the abaqus-static-analysis, abaqus-mesh, abaqus-job, and abaqus-odb skills. Build a complete Abaqus static-analysis workflow, run it if the Abaqus MCP or local Abaqus CLI is available, and report the exact files and commands used.
```

## Text to CAE Viewer

Viewer 仍作为浏览器结果检查层保留。只要案例包含 `result_mesh.json`，即使没有安装求解器也可以查看。

```powershell
Set-Location .\viewer
npm.cmd install
npm.cmd run dev
```

打开 Vite 输出的地址，通常是：

```text
http://127.0.0.1:4178/
```

示例案例：

```text
http://127.0.0.1:4178/?case=cantilever
http://127.0.0.1:4178/?case=hole-plate
http://127.0.0.1:4178/?case=hole-plate-modal
http://127.0.0.1:4178/?case=sphere-impact
http://127.0.0.1:4178/?case=milling-3d
http://127.0.0.1:4178/?case=gear-mesh
http://127.0.0.1:4178/?case=bullet-plate
```

## 仓库结构

```text
CAE-Agent-Hub/
  MCP/
    Abaqus/
    CalculiX/
    Ansys/
      AEDT MCP/
      Fluent MCP/
      Workbench MCP/
  Skill/
    calculix/
    abaqus/
      core/
      modeling/
      setup/
      analysis/
      execution/
      postprocessing/
      optimization/
      reference/
  models/
  viewer/
```

## 源码管理规则

仓库应该包含可复用源码、文档、测试、示例、模板和 skill instruction。

仓库不应该包含：

- CAE 软件二进制文件或许可证。
- 私有机器路径或凭据。
- 虚拟环境和包缓存。
- 生成的求解器输出，例如 ODB、case/data、AEDT results、Workbench project、日志和截图。
- 可以重新生成的大型本地结果文件。

## 构建

构建前端 viewer：

```powershell
Set-Location .\viewer
npm.cmd run build
```

## 路线图

这个 Hub 会继续扩展到更多主流仿真生态：

- 更多求解器专用 MCP server。
- 更多产品化 skill pack，用于可复用建模和验证工作流。
- 面向 viewer 和报告生成的共享结果导出格式。
- 每个 CAE 应用的安装提示词和验证脚本。
