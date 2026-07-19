# HyperWorks MCP

用于让 Codex 通过可审计、限定工作区的工具控制本机 Altair HyperWorks 2026。

当前 0.2 版已实现混合架构：

- 自动发现 HyperMesh GUI、`hmbatch`、HyperStudy、OptiStruct 和 Radioss。
- 创建隔离项目并导入 CAD、`.hm`、`.fem`、`.rad` 或结果文件。
- 写入经过安全检查的 HyperMesh Tcl 脚本。
- 异步运行 HyperMesh Batch，返回任务 ID，而不是阻塞 MCP。
- 启动 HyperMesh 或 HyperView 图形界面。
- 异步提交 OptiStruct/Radioss，限制 CPU 数并复制完整项目输入目录。
- 查询实际进程状态、读取日志、取消任务、列出产物。
- FastMCP tools、resources 和标准预处理/求解 prompt。
- HyperWorks Python Extension，通过随机令牌保护的 `127.0.0.1` 桥接访问实时会话。
- 在 Qt 主线程执行 `hm` API，socket 工作线程不直接操作模型。
- 实时读取会话、模型、实体、用户 mark、质量/质量中心等模型信息。
- 交互式实体选择、实体属性修改、受控创建节点/单元/材料，以及实时视图刷新。
- 从 MCP 项目输入目录显式载入 `.hm` 模型，并将实时模型安全保存到 MCP 工作区。

## 查找你的 HyperWorks 安装目录

不要照抄其他计算机的安装路径。`HYPERWORKS_HOME` 应指向包含 `hwdesktop` 的 Altair
版本目录；安装求解器后，该目录通常还包含 `hwsolvers`。典型目录结构如下：

```text
<HYPERWORKS_INSTALL_ROOT>\
  hwdesktop\hwx\bin\win64\runhwx.exe
  hwdesktop\hm\bin\win64\hmbatch.exe
  hwdesktop\hst\bin\win64\hstbatch.exe
  hwsolvers\scripts\optistruct.bat        # 可选
  hwsolvers\scripts\radioss.bat           # 可选
```

优先查看 HyperWorks/HyperMesh 桌面快捷方式属性中的**目标**。也可以用 PowerShell
搜索 Windows 常见安装位置：

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

如果安装在自定义位置，请把其上级目录作为搜索范围。将搜索结果末尾的
`\hwdesktop\hwx\bin\win64\runhwx.exe` 去掉，即得到
`<HYPERWORKS_INSTALL_ROOT>`。`probe_environment.py` 会根据当前计算机的实际安装，
报告桌面、批处理及求解器能力；不会把维护者计算机上的探测结果当成通用结论。

## 安装

在本目录执行：

```powershell
uv sync --extra dev
```

环境探测：

```powershell
$env:HYPERWORKS_HOME = '<HYPERWORKS_INSTALL_ROOT>'
$env:HYPERWORKS_MCP_WORKSPACE = Join-Path `
  ([Environment]::GetFolderPath('MyDocuments')) 'HyperWorksMCP\workspace'
.\.venv\Scripts\python.exe .\probe_environment.py
```

运行测试：

```powershell
$env:PYTHONPATH = 'src'
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe .\stdio_smoke.py
# 以下命令会短暂启动 hmbatch 并可能占用许可证
.\.venv\Scripts\python.exe .\hmbatch_smoke.py --run
```

## 注册到 Codex

可复制 [`examples/codex_config.example.toml`](examples/codex_config.example.toml) 到
Codex 配置，或执行：

```powershell
.\register_codex_mcp.ps1 `
  -PythonExe "$PWD\.venv\Scripts\python.exe" `
  -HyperWorksHome $env:HYPERWORKS_HOME `
  -Workspace $env:HYPERWORKS_MCP_WORKSPACE
```

重启 Codex 或新建任务后，先调用 `get_environment` 验证真实能力。

## 安装内嵌 Python Extension

```powershell
.\install_hyperworks_extension.ps1 `
  -Workspace $env:HYPERWORKS_MCP_WORKSPACE
```

安装器会：

1. 将 Extension 复制到当前用户文档目录下的 `Altair\CustomPlugins\HyperWorksMCP`。
2. 在 `%LOCALAPPDATA%\HyperWorksMCP\bridge.json` 创建随机 256-bit 令牌。
3. 将 MCP 工作区设为实时模型唯一允许保存的根目录。
4. 将 `HyperWorks MCP Bridge` 写入当前用户的 Altair Extension 注册表。

重启 HyperMesh；若扩展未自动启用，在 `File > Extension Manager` 中打开
`HyperWorks MCP Bridge` 的开关。验证：

```powershell
.\.venv\Scripts\python.exe .\probe_live_bridge.py
```

Extension 使用固定白名单协议，不提供 `eval`、任意 Python、shell 或 Tcl。每个请求都
验证令牌，socket 线程只负责 JSON 收发，实际 `hm` 调用由 Qt 定时器在应用主线程执行。

## 推荐工作流

1. `get_environment`
2. `create_project`
3. `import_project_file`
4. `write_tcl_script`
5. 用户确认后调用 `run_hmbatch`
6. `get_job_status` 与 `tail_job_log`
7. `list_job_artifacts`
8. 求解器可用且用户确认后调用 `submit_solver_job`

示例 Tcl（只验证批处理链路）：

```tcl
puts "HyperWorks MCP batch smoke test"
```

不要在脚本中写 `*quit`；MCP 运行器负责脚本结束。为避免借 Tcl 绕过 MCP 权限，
进程/网络/动态加载、直接 Tcl 文件访问、绝对路径、父目录跳转、环境变量访问和嵌套
`source` 会被拒绝。该过滤器属于纵深防御，不是操作系统级沙箱，运行前仍应审查脚本。

## 工具列表

- `get_environment`
- `configure_installation`
- `create_project`
- `get_project_summary`
- `import_project_file`
- `write_tcl_script`
- `run_hmbatch`
- `launch_hypermesh`
- `submit_solver_job`
- `get_job_status`
- `tail_job_log`
- `cancel_job`
- `list_jobs`
- `list_job_artifacts`
- `get_live_bridge_status`
- `get_live_capabilities`
- `get_live_session_info`
- `get_live_model_summary`
- `list_live_entities`
- `get_live_entity`
- `get_live_user_mark`
- `select_live_entities_interactively`
- `set_live_entity_attributes`
- `create_live_nodes`
- `create_live_elements`
- `create_live_material`
- `load_live_model`
- `refresh_live_view`
- `get_live_model_metrics`
- `save_live_model`

## 当前边界

0.3 版已加入受控实时建模：单次最多创建 5000 个节点或单元，单元必须引用已存在的
正整数节点 ID，材料属性数量受限；模型载入仅接受 MCP 项目输入目录中的 `.hm` 文件，
并要求显式设置 `replace_current=true`。视图刷新只执行固定的 `hm_viewfit` 和
`hm_redraw`，没有开放任意 Python 或 Tcl。HyperView 云图、结果查询和截图的专用
handler 尚未加入，`hw.hv` 可用性已纳入实时能力探测。
