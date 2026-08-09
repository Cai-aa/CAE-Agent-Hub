# ANSYS Workbench MCP

这个目录包含一个可移植的 MCP 服务器，以及一个用于 ANSYS Mechanical 的 ACT 桥接插件。它可以让支持 MCP 的客户端控制 Workbench 和 Mechanical。

本目录只保留可复用的源码和配置模板，不包含本机虚拟环境、作业输出、队列响应、求解结果数据库或用户私有路径。

## 内容

- `server.py` 暴露 Workbench、Mechanical、文件队列和 socket timer 相关 MCP 工具。
- `tools/` 包含 Python 侧工具，用于启动 Workbench 作业并和 Mechanical 通信。
- `workbench_plugin/` 包含加载到 ANSYS Mechanical 的 ACT 扩展。
- `.env.example` 说明每台机器需要设置的环境变量。
- `examples/codex_config.example.toml` 提供 Codex MCP 配置示例。

## 安装

在本目录下执行：

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -U pip
.\.venv\Scripts\python.exe -m pip install -e .[mechanical]
```

复制 `.env.example` 为 `.env`，然后填入你本机的 ANSYS 路径。

## MCP 客户端安装提示词

把下面对应客户端的提示词复制到支持 MCP 的客户端里使用。请把 `<repo>` 替换成本目录的绝对路径，例如 `C:\path\to\text-to-cae\MCP\Ansys\Workbench MCP`。

### Codex

```text
请为 Codex 安装这个本地 ANSYS Workbench MCP server。

项目目录：
<repo>

请在 Codex MCP 配置里添加一个名为 `ansys-workbench` 的 stdio server：
- command: <repo>\.venv\Scripts\python.exe
- args: ["<repo>\server.py"]
- cwd: <repo>
- env:
  - ANSYS_ROOT=<你的 ANSYS 安装根目录，例如 C:\Program Files\ANSYS Inc\v261>
  - WORKBENCH_MCP_ROOT=<repo>
  - WORKBENCH_MCP_QUEUE_ROOT=<repo>\workbench_queue
  - WORKBENCH_MCP_HOST=127.0.0.1
  - WORKBENCH_MCP_PORT=9885

如果虚拟环境还不存在，请先创建并安装依赖：
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -U pip
.\.venv\Scripts\python.exe -m pip install -e .[mechanical]

配置完成后，请通过列出 MCP tools 来验证，并运行 `workbench_detect_tool`。
```

### Claude Code

```text
请把这个本地 ANSYS Workbench MCP server 添加到 Claude Code。

项目目录：
<repo>

使用名为 `ansys-workbench` 的 stdio MCP server：
- command: <repo>\.venv\Scripts\python.exe
- args: ["<repo>\server.py"]
- cwd: <repo>
- env:
  - ANSYS_ROOT=<你的 ANSYS 安装根目录>
  - WORKBENCH_MCP_ROOT=<repo>
  - WORKBENCH_MCP_QUEUE_ROOT=<repo>\workbench_queue
  - WORKBENCH_MCP_PORT=9885

如果依赖缺失，请创建 `.venv` 并运行 `pip install -e .[mechanical]`。
然后重启 Claude Code，确认 Workbench MCP tools 已可用。
```

### Claude Desktop

```text
请帮我把这个本地 ANSYS Workbench MCP server 添加到 Claude Desktop。

项目目录：
<repo>

请创建或更新 Claude Desktop 的 MCP 配置，添加如下 stdio server：

"ansys-workbench": {
  "command": "<repo>\\.venv\\Scripts\\python.exe",
  "args": ["<repo>\\server.py"],
  "cwd": "<repo>",
  "env": {
    "ANSYS_ROOT": "<你的 ANSYS 安装根目录>",
    "WORKBENCH_MCP_ROOT": "<repo>",
    "WORKBENCH_MCP_QUEUE_ROOT": "<repo>\\workbench_queue",
    "WORKBENCH_MCP_HOST": "127.0.0.1",
    "WORKBENCH_MCP_PORT": "9885"
  }
}

如果虚拟环境还不存在，请先创建虚拟环境。然后重启 Claude Desktop，并确认 Workbench MCP tools 出现在工具列表里。
```

### Cursor

```text
请在 Cursor 中配置这个本地 ANSYS Workbench MCP server。

项目目录：
<repo>

添加一个名为 `ansys-workbench` 的 stdio MCP server：
- command: <repo>\.venv\Scripts\python.exe
- args: ["<repo>\server.py"]
- cwd: <repo>
- environment:
  - ANSYS_ROOT=<你的 ANSYS 安装根目录>
  - WORKBENCH_MCP_ROOT=<repo>
  - WORKBENCH_MCP_QUEUE_ROOT=<repo>\workbench_queue
  - WORKBENCH_MCP_HOST=127.0.0.1
  - WORKBENCH_MCP_PORT=9885

如果 `.venv` 不存在，请创建虚拟环境并安装依赖：`pip install -e .[mechanical]`。
保存 MCP 设置后，重新加载 Cursor，并执行一次 tool discovery 检查。
```

### 通用 MCP Client

```json
{
  "mcpServers": {
    "ansys-workbench": {
      "command": "<repo>\\.venv\\Scripts\\python.exe",
      "args": ["<repo>\\server.py"],
      "cwd": "<repo>",
      "env": {
        "ANSYS_ROOT": "<你的 ANSYS 安装根目录>",
        "WORKBENCH_MCP_ROOT": "<repo>",
        "WORKBENCH_MCP_QUEUE_ROOT": "<repo>\\workbench_queue",
        "WORKBENCH_MCP_HOST": "127.0.0.1",
        "WORKBENCH_MCP_PORT": "9885"
      }
    }
  }
}
```

## 配置 Mechanical ACT

把插件文件安装到当前 ANSYS 版本对应的 ACT 扩展目录，例如：

```text
%APPDATA%\Ansys\v261\ACT\extensions\WorkbenchMCP.xml
%APPDATA%\Ansys\v261\ACT\extensions\WorkbenchMCP\main.py
%APPDATA%\Ansys\v261\ACT\extensions\WorkbenchMCP\mechanical_queue_processor.py
%APPDATA%\Ansys\v261\ACT\extensions\WorkbenchMCP\mechanical_socket_timer_v7.py
%APPDATA%\Ansys\v261\ACT\extensions\WorkbenchMCP\mechanical_analysis_workflows.py
```

如果 ACT 插件安装在本目录之外，请在启动 Mechanical 之前设置这些环境变量：

```text
WORKBENCH_MCP_ROOT=<本目录路径>
WORKBENCH_MCP_QUEUE_ROOT=<本目录路径>\workbench_queue
WORKBENCH_MCP_PORT=9885
```

打开 Mechanical 后，可以使用 `Workbench MCP` 工具栏：

- `Process MCP Queue`：处理一次待执行的文件队列请求。
- `Socket Timer Start`：启动 localhost socket 桥接。
- `Socket Timer Stop`：停止 socket 桥接。

插件默认会自动启动队列定时器和 socket timer。如需关闭，可设置 `WORKBENCH_MCP_AUTO_START_SOCKET=0` 或 `WORKBENCH_MCP_AUTO_START_QUEUE=0`。

## MCP 工具

服务器提供以下工具：

- 检测 Workbench 和 PyMechanical
- 启动 Workbench journal
- 启动 Mechanical Python 脚本
- 读取作业日志和状态
- 向 Mechanical 提交队列请求
- 通过队列或 socket timer 在当前打开的 Mechanical 会话中执行 Python

### 旋转静力与预应力模态工具

新增工具覆盖完整结构分析链：

- `mechanical_readiness_tool`、`mechanical_probe_session_tool`：确认桥接、`Project`、`Model` 和 `Model.Analyses` 真正可用。
- `workbench_create_prestressed_modal_chain_tool`：创建 Static Structural、零转速 Modal 和预应力 Modal 的 Workbench 项目链。
- `mechanical_geometry_inventory_tool`、`mechanical_import_geometry_tool`：导入几何并返回实体、面/边 ID、命名选择、接触和分析清单。
- `mechanical_create_named_selection_tool`：用明确的几何实体 ID 创建命名选择。
- `mechanical_create_analysis_chain_tool`：在同一个 Mechanical 模型中创建旋转静力、基准模态和预应力模态，并设置预应力来源。
- `mechanical_validate_rotor_job_tool`、`mechanical_configure_rotor_model_tool`：校验并设置材料、绑定接触、固定约束、旋转轴和转速。
- `mechanical_validate_mesh_job_tool`、`mechanical_mesh_and_validate_tool`：设置全局/局部网格并返回节点和单元证据。
- `mechanical_solve_analysis_tool`、`mechanical_workflow_status_tool`：按顺序提交求解并轮询长任务；超时后禁止立即重复提交。
- `mechanical_extract_structural_results_tool`、`mechanical_extract_modal_results_tool`：提取应力、变形、频率和预应力频移。
- `mechanical_export_evidence_tool`：导出结果图片和表格，支持 `error | versioned | replace`，默认 `error`。

所有会修改 Mechanical 数据模型的工具默认使用 `transport="queue"`，由 Mechanical UI 主线程执行。`transport="socket"` 仅建议用于只读诊断或已明确验证支持的轻量操作。

推荐调用顺序：

```text
mechanical_readiness_tool
  -> mechanical_probe_session_tool
  -> mechanical_import_geometry_tool
  -> mechanical_geometry_inventory_tool
  -> mechanical_create_named_selection_tool
  -> mechanical_create_analysis_chain_tool
  -> mechanical_validate_rotor_job_tool
  -> mechanical_configure_rotor_model_tool
  -> mechanical_validate_mesh_job_tool
  -> mechanical_mesh_and_validate_tool
  -> mechanical_solve_analysis_tool
  -> mechanical_workflow_status_tool
  -> mechanical_extract_structural_results_tool
  -> mechanical_extract_modal_results_tool
  -> mechanical_export_evidence_tool
```

旋转静力参数示例：

```json
{
  "analysis_name": "Rotating_Static",
  "rotational_speed_rpm": 6000,
  "rotation_axis": "X",
  "fixed_support_named_selection": "Disk_Bore",
  "contact_mode": "existing",
  "expected_contact_count": 20,
  "material_name": "Structural Steel",
  "large_deflection": true
}
```

先调用校验工具。材料、转速、命名选择和接触数量必须来自已确认的模型或教学任务单，不应由 MCP 自动猜测。
完整的旋转模型和网格输入示例见 `examples/rotor_analysis.example.json`。

运行离线测试：

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
python -m unittest discover -s tests -v
```

## 说明

本项目仍然需要用户机器上有可用且授权的 ANSYS 安装。它不包含 ANSYS 二进制文件、求解结果文件或私有本机配置。
