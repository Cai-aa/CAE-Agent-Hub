# ANSYS Fluent MCP

这个目录包含一个可移植的 ANSYS Fluent MCP server，用于让支持 MCP 的客户端控制本机 Fluent。结构参考 `MCP/Ansys/Workbench MCP`，但功能聚焦在 Fluent：

- 通过 `fluent.exe` 执行 batch journal
- 跟踪作业元数据和 stdout/stderr 日志
- 可选通过 PyFluent 启动实时会话，执行 Scheme、TUI 和 Python 侧探测

本目录只保留可复用源码和配置模板，不包含 ANSYS 二进制文件、许可证、case/data 文件、本机虚拟环境或生成的求解结果。

## 内容

- `server.py`：通过 stdio 暴露 Fluent MCP tools。
- `tools/fluent_bridge.py`：检测 Fluent，并启动 batch journal 作业。
- `tools/pyfluent_session.py`：管理可选的实时 PyFluent 会话。
- `.env.example`：说明本机需要设置的环境变量。
- `examples/codex_config.example.toml`：Codex MCP 配置示例。
- `tests/`：工具层的标准库单元测试。

## 安装

在本目录下执行：

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -U pip
.\.venv\Scripts\python.exe -m pip install -e .[pyfluent]
```

如果只需要检测 Fluent 和启动 batch journal，可以只安装基础依赖：

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
```

复制 `.env.example` 为 `.env`，然后填入本机 ANSYS 路径。

## MCP 客户端安装提示词

把 `<repo>` 替换成本目录的绝对路径，例如 `C:\path\to\text-to-cae\MCP\Ansys\Fluent MCP`。

### Codex

```text
请为 Codex 安装这个本地 ANSYS Fluent MCP server。

项目目录：
<repo>

请在 Codex MCP 配置里添加一个名为 `ansys-fluent` 的 stdio server：
- command: <repo>\.venv\Scripts\python.exe
- args: ["<repo>\server.py"]
- cwd: <repo>
- env:
  - ANSYS_ROOT=<你的 ANSYS 安装根目录，例如 C:\Program Files\ANSYS Inc\v261>
  - FLUENT_EXE=<fluent.exe 的路径>
  - FLUENT_MCP_JOBS_DIR=<repo>\jobs

如果虚拟环境还不存在，请先创建并安装依赖：
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -U pip
.\.venv\Scripts\python.exe -m pip install -e .[pyfluent]

配置完成后，请通过列出 MCP tools 来验证，并运行 `fluent_detect_tool`。
```

### 通用 MCP Client

```json
{
  "mcpServers": {
    "ansys-fluent": {
      "command": "<repo>\\.venv\\Scripts\\python.exe",
      "args": ["<repo>\\server.py"],
      "cwd": "<repo>",
      "env": {
        "ANSYS_ROOT": "<你的 ANSYS 安装根目录>",
        "FLUENT_EXE": "<fluent.exe 的路径>",
        "FLUENT_MCP_JOBS_DIR": "<repo>\\jobs"
      }
    }
  }
}
```

## MCP Tools

- `fluent_detect_tool`：检测 `fluent.exe`、`ANSYS_ROOT`、作业目录和 `ansys-fluent-core`。
- `fluent_run_journal_tool`：通过 `fluent.exe` 异步启动 Fluent journal。
- `fluent_job_status_tool`：查看已启动 Fluent 作业的状态。
- `fluent_job_log_tool`：读取作业 stdout 或 stderr 尾部日志。
- `fluent_list_jobs_tool`：列出最近 Fluent 作业。
- `fluent_launch_session_tool`：启动由 MCP 进程持有的实时 PyFluent 会话。
- `fluent_list_sessions_tool`：列出实时 PyFluent 会话。
- `fluent_session_info_tool`：读取 PyFluent 会话基础信息。
- `fluent_execute_scheme_tool`：在 Fluent 中执行小段 Scheme 表达式。
- `fluent_run_tui_tool`：在实时 PyFluent 会话中执行 Fluent TUI 命令。
- `fluent_run_python_tool`：在 MCP 进程中执行 Python，变量 `session` 指向 PyFluent 会话。
- `fluent_close_session_tool`：关闭实时 PyFluent 会话。

## 示例流程

### Batch journal

```text
1. 调用 `fluent_detect_tool`。
2. 在干净 case 目录中准备 Fluent journal 文件。
3. 调用 `fluent_run_journal_tool`，传入 `journal_path`。
4. 用 `fluent_job_status_tool` 轮询状态。
5. 如果作业异常退出，用 `fluent_job_log_tool` 查看日志。
```

默认 batch 命令等价于：

```powershell
fluent.exe 3ddp -g -t2 -i case.jou
```

### 实时 PyFluent

```text
1. 调用 `fluent_detect_tool`，确认 `pyfluent.available` 为 true。
2. 调用 `fluent_launch_session_tool`。
3. 调用 `fluent_session_info_tool`。
4. 用 `fluent_execute_scheme_tool` 执行 `(+ 2 3)` 验证会话。
5. 先用小段 TUI 或 Python 探测，再进行更大的求解器设置。
6. 完成后调用 `fluent_close_session_tool`。
```

## 测试

本目录测试只依赖 Python 标准库：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## 说明

真实求解需要本机已有可用且授权的 ANSYS Fluent。PyFluent 工具启动的会话由 MCP server 进程持有；如果 MCP 客户端重启 server，会话需要重新启动。
