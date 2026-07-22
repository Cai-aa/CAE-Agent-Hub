# HyperWorks MCP

这是一个面向 Altair HyperWorks 的本地 FastMCP 服务，以独立工作区为安全边界，提供可审计的建模、网格、求解和后处理能力。0.10.0 采用“外部 MCP 服务 + HyperWorks 内嵌 Python Extension”的混合架构，不开放任意 Python、Tcl、Shell、PowerShell 或 `eval`。

## 0.10.0 主要能力

- 检测 HyperMesh、HyperStudy、OptiStruct 和 Radioss 的真实安装与启动器。
- 查询、修改、载入、保存当前 HyperMesh 模型，并刷新视图。
- 创建节点、单元、材料、实体块、实体圆柱以及受控圆柱 O-grid。
- 导入工作区内的 STEP、IGES、Parasolid。
- 执行曲面自动网格、Solid Map 和原生结构四面体网格。
- 检查网格质量，并通过受控平滑执行第一版质量修复。
- 创建 Property、Loadcol、Loadstep、Set、Constraint 和接触相关求解卡实体。
- 创建力、力矩、约束、温度、热流、速度、加速度和压力。
- 创建刚性连接、RBE3、节点焊接、带 Property 的点焊，以及尚未 Realize 的 Spot/Seam/Area/Bolt Connector 意图。
- 运行 OptiStruct 线性静力和 Radioss 显式块体冲击验证模板。
- 管理异步求解任务、日志、取消和结果产物。
- 审计 Radioss 终止、能量、添加质量、时间步、负体积和穿透信号。
- 在 HyperView 中读取结果、查询云图、选择首帧/末帧/指定帧并导出 PNG。
- 遍历结果帧，在 HyperGraph 中生成时序曲线，同时导出 CSV 和 PNG。
- 生成包含真实任务状态、结果产物和质量审计的 HTML/JSON 报告。
- 通过注册库发现并调用可复用求解器分析模板。

所有模型修改和网格操作都会先创建 `.hm` 检查点；操作失败时自动回滚。

## 1. 找到本机 HyperWorks 安装根目录

不要复制其他用户电脑上的安装路径。`HYPERWORKS_HOME` 应指向同时包含 `hwdesktop`，并在安装求解器时包含 `hwsolvers` 的 Altair 版本目录：

```text
<HYPERWORKS_INSTALL_ROOT>\
  hwdesktop\hwx\bin\win64\runhwx.exe
  hwdesktop\hm\bin\win64\hmbatch.exe
  hwdesktop\hst\bin\win64\hstbatch.exe
  hwsolvers\scripts\optistruct.bat       # 可选
  hwsolvers\scripts\radioss.bat          # 可选
```

可以查看 HyperWorks/HyperMesh 快捷方式的“目标”，也可以在常见安装目录中搜索 `runhwx.exe`：

```powershell
$searchRoots = @(
  "$env:ProgramFiles\Altair"
  "$env:ProgramW6432\Altair"
  "$env:SystemDrive\Altair"
) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -Unique

Get-ChildItem -Path $searchRoots -Filter runhwx.exe -File -Recurse `
  -ErrorAction SilentlyContinue |
  Where-Object FullName -Match '\\hwdesktop\\hwx\\bin\\win64\\runhwx\.exe$' |
  Select-Object -ExpandProperty FullName
```

从结果中去掉末尾的 `\hwdesktop\hwx\bin\win64\runhwx.exe`，即可得到安装根目录。

## 2. 安装与本地验证

```powershell
uv sync --extra dev
$env:HYPERWORKS_HOME = '<HYPERWORKS_INSTALL_ROOT>'
$env:HYPERWORKS_MCP_WORKSPACE = Join-Path `
  ([Environment]::GetFolderPath('MyDocuments')) 'HyperWorksMCP\workspace'
$env:PYTHONPATH = 'src'

.\.venv\Scripts\python.exe .\probe_environment.py
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe .\stdio_smoke.py
```

`hmbatch_smoke.py --run`、`optistruct_e2e_smoke.py` 和 `radioss_e2e_smoke.py` 会启动真实 Altair 程序并可能消耗许可证，只应在获得许可后运行。

## 3. 全局注册到 Codex

参考 [`examples/codex_config.example.toml`](examples/codex_config.example.toml)，或执行：

```powershell
.\register_codex_mcp.ps1 `
  -PythonExe "$PWD\.venv\Scripts\python.exe" `
  -HyperWorksHome $env:HYPERWORKS_HOME `
  -Workspace $env:HYPERWORKS_MCP_WORKSPACE
```

重启 Codex 后先调用 `get_environment`，同时确认 MCP 已注册、服务可启动、桌面程序及求解器启动器真实存在。

## 4. 安装 HyperWorks 内嵌 Extension

```powershell
.\install_hyperworks_extension.ps1 `
  -Workspace $env:HYPERWORKS_MCP_WORKSPACE
```

安装器会复制 Extension、生成随机令牌并注册 `HyperWorks MCP Bridge`。随后由用户自行重启 HyperMesh，或在 `File > Extension Manager` 中重新加载扩展。本项目不依赖电脑控制功能点击界面。

重载后验证：

```powershell
.\.venv\Scripts\python.exe .\probe_live_bridge.py
```

实时桥只绑定 `127.0.0.1`，每个请求都校验令牌，并且只允许固定方法。文件读写被限制在 MCP 工作区中。

## 5. 通用前处理链

推荐顺序：

1. `create_project`
2. `import_project_file` 和 `import_live_cad`
3. `automesh_live_surfaces`、`tetra_mesh_live_solids`、`solid_map_live_solids` 或 `create_live_cylindrical_ogrid`
4. `get_live_mesh_quality`，必要时调用 `repair_live_mesh_quality`
5. `create_live_material`
6. `create_live_solver_card_entity` 创建 Property、Loadcol 或接触卡
7. `create_live_nodal_load` 或 `create_live_pressure_load`
8. `create_live_loadstep`
9. 需要装配连接时，使用 `create_live_connector` 建立 Connector 意图，或使用已验证的刚性连接、RBE3、焊接接口
10. `save_live_model`

卡片名称和 Data Name 仍取决于当前求解器配置。MCP 不会猜测某个 OptiStruct、Radioss 或其他求解器卡片的字段含义。

## 6. 可复用分析模板

- `list_analysis_templates`：列出模板及验证状态。
- `get_analysis_template`：读取模板所需参数。
- `prepare_analysis_template`：通过统一入口准备输入 Deck。

0.10.0 内置以下经过真实求解验证的模板：

- `optistruct.linear_static_solid`
- `optistruct.normal_modes_solid`
- `optistruct.linear_buckling_solid`
- `optistruct.multi_case_static_solid`
- `optistruct.gap_contact_static_solid`
- `optistruct.uniform_thermal_stress_solid`
- `radioss.explicit_block_impact`
- `radioss.plate_impact_solid`
- `radioss.drop_weight_solid_surrogate`
- `radioss.solid_axial_collision`

两个带 `surrogate` 的条目是受控实体、初速度替代夹具，不代表重力落锤，也不代表薄壁壳碰撞盒。`radioss.three_point_bending`、`radioss.tube_crush`、`radioss.thin_wall_axial_collision`、`radioss.vehicle_crash_subsystem` 和 `hyperstudy.template_doe_optimization` 可以被发现和审计，但当前会明确返回“不可运行”；在对应几何夹具或求解器耦合适配器完成前，MCP 不会用两块实体模型冒充这些物理试验。

模板库用于把已验证的材料、属性、网格、载荷、约束、接触、控制和输出组合复用到后续任务中，并不代表任意模型都能直接套用。

## 7. 后处理、HyperGraph 与报告

完成求解后：

1. `get_solver_result_artifacts` 分类实际结果文件。
2. Radioss 作业调用 `audit_radioss_explicit_job`。
3. `postprocess_solver_result_in_hyperview` 生成云图、极值、实体查询和 PNG。
4. `extract_solver_time_history_in_hypergraph` 遍历全部结果帧，输出 CSV、HyperGraph 曲线和 PNG。
5. `generate_solver_job_report` 输出 HTML 与 JSON 证据报告。

## 8. 仍然存在的边界

- 草图尺寸约束、通用拉伸/旋转/扫掠/放样、布尔、圆角和自动去特征尚未形成安全的类型化工具链。
- 四面体网格已开放；任意复杂实体的全自动六面体分块和通用 O-grid 拓扑规划仍未完成。
- 当前质量修复主要是受控节点平滑，不等同于覆盖所有 2D/3D 失效模式的自动重网格专家系统。
- Connector 意图创建和点焊已经开放；通用 Connector Realization 仍需要求解器专用 FE 类型、Property 和控制参数。HyperMesh 原生 Fastener 创建接口目前仅支持 Abaqus 配置，因此不会在 OptiStruct/Radioss 中伪装成通用能力。
- 假人、安全带、气囊折叠与缝合仍处于能力审计状态。
- 目前直接提交的求解器是 OptiStruct 和 Radioss。
- 通用求解卡接口要求调用者提供当前求解器真实存在的 Card Image 和 Data Name；错误字段会由 HyperMesh 拒绝并触发回滚。

更多设计与安全边界见 [ARCHITECTURE.md](ARCHITECTURE.md) 和 [ADVANCED_CAPABILITY_AUDIT.md](ADVANCED_CAPABILITY_AUDIT.md)。
