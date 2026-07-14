# Abaqus MCP

这个目录包含一个可移植的 MCP server，以及一个低延迟的 Abaqus/CAE socket bridge。支持 MCP 的客户端可以通过它控制正在运行的 Abaqus/CAE：执行 Abaqus Python、查看模型、列出和提交作业、监控求解文件、读取 ODB 元数据，并抓取视口图片。

v5 版本把旧的 `commands/`、`results/` 文件队列通信替换成了本地 TCP bridge，通信模型与 [Whfkl/Abaqus-Control-MCP](https://github.com/Whfkl/Abaqus-Control-MCP) 一致。当前实现保留了本项目原有的 Abaqus 工具名，方便已有 MCP 客户端继续使用，同时新增更适合实时交互的 `run_python`、`set_workdir`、`monitor_job_status`、`inspect_odb`、`capture_viewport` 工作流。

本目录只包含可复用源码和配置模板，不包含运行日志、求解输出、ODB、截图、虚拟环境或私有本机路径。

## 目录内容

- `mcp_server.py`：在 Abaqus 外部运行，通过 stdio 暴露 MCP tools。
- `abaqus_mcp_plugin.py`：在 Abaqus/CAE 内部运行，启动 TCP socket bridge。
- `abaqus_plugins/mcp_control/`：Abaqus GUI 菜单加载器。
- `stop_mcp.py`：向正在运行的 socket bridge 发送停止请求。
- `abaqus_v6.env.example`：示例 Abaqus 启动环境文件，用于启动时自动加载菜单。
- `.env.example`：说明 socket、超时和插件路径环境变量。
- `examples/mcp_config.example.json`：通用 MCP 客户端配置示例。
- `THIRD_PARTY_NOTICES.md`：记录上游 MIT 许可归属说明。

## 架构

```text
MCP client
  <stdio MCP>
mcp_server.py
  <local TCP JSON, default 127.0.0.1:48152>
Abaqus/CAE GUI bridge
  <AFX timeout dispatcher + sendCommand>
Abaqus kernel
```

bridge 在 Abaqus GUI 线程上处理请求，再通过 `sendCommand` 到 Abaqus kernel 执行代码。这样不再轮询命令文件，短脚本探测和交互式建模会更实时。

## 安装

在本目录运行：

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -U pip
.\.venv\Scripts\python.exe -m pip install -e .
```

如需覆盖默认值，在 MCP 客户端配置里设置：

```text
ABAQUS_MCP_HOST=127.0.0.1
ABAQUS_MCP_PORT=48152
ABAQUS_MCP_TIMEOUT=60
ABAQUS_MCP_HOME=<repo>
```

如果使用可选的 Abaqus GUI 菜单加载器，`ABAQUS_MCP_HOME` 应该指向本目录。

## MCP 客户端配置

把 `<repo>` 替换为本目录的绝对路径，例如 `C:\path\to\text-to-cae\MCP\Abaqus`。

```json
{
  "mcpServers": {
    "abaqus-mcp-server": {
      "command": "<repo>\\.venv\\Scripts\\python.exe",
      "args": ["<repo>\\mcp_server.py"],
      "cwd": "<repo>",
      "env": {
        "ABAQUS_MCP_HOST": "127.0.0.1",
        "ABAQUS_MCP_PORT": "48152",
        "ABAQUS_MCP_TIMEOUT": "60",
        "ABAQUS_MCP_HOME": "<repo>"
      }
    }
  }
}
```

## 配置 Abaqus/CAE

### 方式 1：启动时自动加载

把 `abaqus_v6.env.example` 复制为 Abaqus 启动环境文件，并把 `ABAQUS_MCP_HOME` 设为本目录。

Windows 示例：

```powershell
$env:ABAQUS_MCP_HOME = "<repo>"
Copy-Item "<repo>\abaqus_v6.env.example" "$env:USERPROFILE\abaqus_v6.env"
```

重启 Abaqus/CAE 后，通过菜单启动：

```text
Plug-ins > Abaqus MCP > Start Socket Bridge
```

### 方式 2：安装 GUI 菜单加载器

把 `abaqus_plugins/mcp_control` 复制到 Abaqus 用户插件目录：

```powershell
Copy-Item -Recurse "<repo>\abaqus_plugins\mcp_control" "$env:USERPROFILE\abaqus_plugins\mcp_control"
```

设置 `ABAQUS_MCP_HOME=<repo>`，重启 Abaqus/CAE，然后从 Plug-ins 菜单启动 bridge。

## MCP Tools

- `ping`：验证 socket bridge，并返回 live session telemetry。
- `check_abaqus_connection`：返回适合阅读的连接状态。
- `run_python`：执行 Abaqus Python，并返回结构化结果和错误诊断。
- `execute_script`：兼容旧版工具名，底层调用 `run_python`。
- `set_workdir`：在建模或提交作业前切换 Abaqus 工作目录。
- `get_model_info`：查看模型、部件、集合、表面、作业和视口。
- `list_jobs`：列出当前 CAE session 中的作业。
- `submit_job`：提交已有作业并等待完成。
- `monitor_job_status`：列出作业，或读取 `.sta`、`.msg` 的尾部诊断。
- `inspect_odb`：读取 ODB 元数据和可用输出变量。
- `get_odb_info`：兼容旧版工具名，底层调用 `inspect_odb`。
- `capture_viewport`：以结构化 base64 数据返回视口截图。
- `get_viewport_image`：兼容旧版工具名，返回 data URI。

资源：

- `abaqus://status`
- `abaqus://session-telemetry`
- `abaqus://agent-instructions`

## 推荐工作流

1. 启动 Abaqus/CAE。
2. 执行 `Plug-ins > Abaqus MCP > Start Socket Bridge`。
3. 在 MCP 客户端调用 `ping`。
4. 调用 `set_workdir`，把 Abaqus 工作目录切到干净的分析文件夹。
5. 用小段 `run_python` 逐步建模和验证。
6. 用 `get_model_info`、`list_jobs`、`monitor_job_status`、`inspect_odb` 检查模型和结果。

## 设计说明

socket dispatcher 和 GUI 线程执行模型参考了 MIT 许可的 `Whfkl/Abaqus-Control-MCP`。本项目保留独立实现，并保留 `text-to-cae` 原有 Abaqus MCP 的兼容工具。

## 说明

本项目需要用户机器上已有可用且授权的 Abaqus/CAE。仓库不包含 Abaqus 二进制文件、求解结果、ODB 文件或私有本机配置。
