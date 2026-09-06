# Ansys AEDT MCP

该模块通过 PyAEDT 让 Codex 等 MCP 客户端控制 Ansys Electronics Desktop。默认并经过实机验收的目标版本是 AEDT 2026 R1。

## 架构

```text
Codex -> FastMCP stdio server -> 外部 PyAEDT broker -> 明确的 AEDT PID 或 gRPC port
```

AEDT 内部不运行 MCP 脚本、socket server、扩展或后台线程。MCP 会为每个明确目标建立一个外部 broker，并在多次命令之间复用同一条 PyAEDT 连接。只有调用 `release_connection`、MCP 退出或 broker 的 stdin 关闭时，broker 才执行 `release_desktop(close_projects=False, close_on_exit=False)`。

AEDT 2026 R1 的 gRPC 会话要求客户端持续存在；如果每条命令后都结束 PyAEDT 客户端，对应 gRPC 监听也会消失。外部 broker 既避免每次工具调用重建 AEDT，也不会在 AEDT 内留下 Toolkit/Automation 脚本状态。

在 Windows 上，broker 只监视它所连接的目标 AEDT 进程。如果出现 busy 弹窗，或主窗口从可见变为关闭，broker 会把它视为用户明确发出的关闭请求，通过现有 PyAEDT 会话调用 AEDT `QuitApplication()`，随后退出 broker，避免留下无窗口的 AEDT 进程。

## 安装

使用 Python 3.10 或更高版本：

```powershell
py -3.10 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -U pip
.\.venv\Scripts\python.exe -m pip install -e .
```

项目固定使用 PyAEDT 1.5.0，与本适配器对齐的官方 PyAEDT MCP 能力基线一致。使用 `launch_aedt` 时，`AEDT_INSTALL_DIR` 必须指向包含 `ansysedt.exe` 的目录。

## MCP 配置

参考 `examples/mcp_config.example.json`，把 `<repo>` 替换为本目录的绝对路径。

## 明确指定目标

系统没有隐式默认 AEDT 会话。

1. 调用 `check_aedt_installed` 和 `check_aedt_status`。
2. 调用 `list_aedt_sessions`、`connect_to_aedt` 或 `launch_aedt`。
3. 明确选择一个 PID 或一个 gRPC port。
4. 每个目标工具必须且只能传入 `pid` 或 `port` 之一。

服务器不会自动选择最近启动或前台窗口。探测成功后，返回的 PID 和 port 会登记为同一个 broker 的别名，因此后续可以继续使用任一明确标识访问同一会话。

## 生命周期

- `connect_to_aedt` 或 `check_aedt_connection` 在首次使用时创建 broker，并执行真实 PyAEDT 探测。
- 工程和仿真工具复用该 broker。
- `disconnect_from_aedt` 要求明确选择是否关闭 AEDT；`release_connection` 始终保留 AEDT 窗口。
- MCP 正常退出或 broker stdin 关闭时也会释放全部连接。
- 直接关闭 AEDT 窗口会触发 `QuitApplication()`，并结束该目标的 broker。
- broker 超时只会结束 broker，不会强制结束 AEDT。

通过 MCP 启动的会话优先使用 `launch_aedt` 返回的 port。用户手动打开的 AEDT 应从 `list_aedt_sessions` 中选择 PID。

## 工具

与官方 PyAEDT MCP 同名的工具：

- 生命周期与诊断：`check_aedt_installed`、`check_aedt_status`、`launch_aedt`、`connect_to_aedt`、`disconnect_from_aedt`、`clear_aedt`、`get_pyaedt_logs`。
- 工程与设计：`list_projects`、`list_designs`、`open_project`、`save_project`、`create_design`。
- 自动化：`run_python_code`、`run_python_script`。
- 仿真与证据：`validate_design`、`analyze_design`、`export_results`、`export_config`、`get_model_info`、`screenshot`、`get_guidelines_for`。

`create_design` 支持 `Hfss`、`Maxwell2d`、`Maxwell3d`、`Q3d`、`Q2d`、`Icepak`、`Circuit`、`TwinBuilder`、`Mechanical`、`Emit`、`RMXprt` 和 `Hfss3dLayout`。

保留的本地扩展：

- `list_aedt_sessions`、`check_aedt_connection`、`release_connection`：明确目标的 broker 控制。
- `get_project_info`、`close_projects`：结构化工程检查和限定范围的清理。
- `create_hfss_design`、`start_analysis`、`get_analysis_status`：原有 HFSS 工作流。
- `build_wr90_waveguide`：专用 WR-90 TE10 建模、校验、求解与导出流程。

## Icepak 示例

1. 用明确的 `pid` 或 `port` 连接。
2. 调用 `create_design(app_type="Icepak", project_name="Cooling", design_name="BoardThermal")`。
3. 使用 `run_python_code` 创建 Icepak 几何、材料、热源、开口、风扇、网格操作、监视器和 setup。
4. 先调用 `validate_design`，再调用 `analyze_design`。
5. 确认求解状态，并复核日志、监视量稳定性、最高温度、质量流量守恒、热平衡、网格/收敛数据和云图。

设计级 `analyze_design` 是非阻塞调用。返回 `started=true` 只证明任务已提交，不能证明求解完成或工程结论有效。

对于 Icepak，未提供自定义 ACF 文件时，`analyze_design` 默认启用 `icepak_safe_mode=true`。此可靠性模式使用单核、禁用 GPU 分配与自动 DSO 设置，并在返回值中同时给出 `requested_resources` 和 `effective_resources`。只有在目标 AEDT 安装上验证过并行配置后，才建议显式设置 `icepak_safe_mode=false`；调用方提供的 `acf_file` 也会优先于安全模式。

对于已求解的 Icepak 设计，`export_results(export_type="convergence")` 会从原生 `.sd` 结果文件提取残差监控历史并写入 CSV；`export_results(export_type="mesh")` 会先导出 solution profile，再把节点数、面数、单元数及正常完成标记写入 CSV。返回值会记录 `export_method`、源文件和解析明细。这两条 Icepak 专用路径绕开了部分 AEDT 版本中不可用的通用 `ExportConvergence` 与 `ExportMeshStats` 调用。

资源 `aedt://status` 与 `aedt://agent-instructions` 不会隐式连接 AEDT。

## 清理旧工具栏

旧版的 `Start AEDT MCP Bridge` 和 `Stop AEDT MCP Bridge` 按钮不再使用。只清理这些已知条目：

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\remove_legacy_aedt_mcp_toolbar.ps1" -AedtRoot "G:\ANSYS206\ANSYS Inc\v261\AnsysEM"
```

## 验证

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\scripts\run_live_acceptance.ps1 -Mode both
```

实机验收覆盖明确 PID/port、同一 broker 连续命令、一次性 HFSS 工程保存，以及 broker 仍连接时正常关闭 AEDT。若出现“being used by another application, script or extension wizard”弹窗，测试会失败。
