# COMSOL MCP

本目录提供一个用于控制 COMSOL Multiphysics 的 MCP server。目标不是先做完整
“自然语言从零建模 DSL”，而是优先支持真实工程里最常用的实时自动化：
打开已有 `.mph` 模型、修改参数、求解、导出图和表格、保存副本。

整体分三层：

- Python MCP server：给 Codex 暴露工具并管理进程状态。
- Java bridge：通过 stdin/stdout 的 JSON line 协议接收命令。
- COMSOL Java API：由 Java bridge 在运行时通过反射加载。

这样即使当前机器没有 COMSOL 或许可证不可用，MCP server 本身也能启动并完成
环境探测和协议测试。

## 目录内容

- `mcp_server.py`：FastMCP stdio server。
- `tools/detect.py`：探测 COMSOL、Java、API jar 和运行目录。
- `tools/bridge_client.py`：启动并控制 MCP 持有的 Java bridge 进程。
- `tools/model_tools.py`：模型、参数、求解、表达式计算和导出工具。
- `bridge/`：Java bridge 源码和 Maven 配置。
- `examples/codex_config.example.toml`：Codex MCP 配置示例。
- `tests/`：不依赖 COMSOL 的单元测试。

## 安装

在本目录执行：

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -U pip
.\.venv\Scripts\python.exe -m pip install -e .[dev]
```

复制 `.env.example` 为 `.env`，并填写本机路径：

```powershell
Copy-Item .env.example .env
```

常用变量：

- `COMSOL_ROOT`：COMSOL Multiphysics 安装根目录。
- `COMSOL_MCP_RUNS_DIR`：MCP 输出模型副本、图片、CSV、job 元数据的目录。
- `COMSOL_MCP_BRIDGE_JAR`：打包后的 Java bridge jar。
- `COMSOL_MCP_BRIDGE_COMMAND`：如果不用 jar，可以直接写完整 bridge 启动命令。

## 构建 Java Bridge

进入 `bridge` 目录打包：

```powershell
Set-Location .\bridge
mvn package
```

真实控制 COMSOL 时，Java 进程需要把 COMSOL Java API jars 放到 classpath。源码通过
反射调用 API，因此不需要在编译时绑定某个固定 COMSOL 版本。典型启动命令：

```powershell
java -cp "bridge\target\comsol-bridge-0.1.0.jar;<COMSOL jar paths>" com.caeagenthub.comsol.ComsolBridge
```

把这条命令写入 `COMSOL_MCP_BRIDGE_COMMAND`。

如果只验证 MCP 到 bridge 的协议，可以使用占位 backend：

```powershell
$env:COMSOL_MCP_PLACEHOLDER_BACKEND="true"
java -jar bridge\target\comsol-bridge-0.1.0.jar
```

占位 backend 不会控制 COMSOL，只用于验证链路。

## Codex 配置

把类似下面的配置加入 `C:\Users\<you>\.codex\config.toml`：

```toml
[mcp_servers.comsol]
command = "E:\\Code\\CAE-Agent-Hub\\MCP\\COMSOL\\.venv\\Scripts\\python.exe"
args = ["E:\\Code\\CAE-Agent-Hub\\MCP\\COMSOL\\mcp_server.py"]
cwd = "E:\\Code\\CAE-Agent-Hub\\MCP\\COMSOL"
env = {
  COMSOL_ROOT = "C:\\Program Files\\COMSOL\\COMSOL62\\Multiphysics",
  COMSOL_MCP_RUNS_DIR = "E:\\Code\\CAE-Agent-Hub\\MCP\\COMSOL\\comsol_runs",
  COMSOL_MCP_BRIDGE_JAR = "E:\\Code\\CAE-Agent-Hub\\MCP\\COMSOL\\bridge\\target\\comsol-bridge-0.1.0.jar"
}
```

## 推荐工具顺序

首次验证建议按这个顺序：

1. `comsol_detect_tool`
2. `comsol_mphserver_status_tool`
3. `comsol_start_mphserver_tool`
4. `comsol_start_bridge_tool`
5. `comsol_bridge_ping_tool`
6. `comsol_connect_tool`
7. `comsol_open_model_tool`
8. `comsol_model_info_tool`
9. `comsol_set_parameter_tool`
10. `comsol_run_study_tool`
11. `comsol_export_plot_tool`
12. `comsol_export_table_tool`
13. `comsol_save_model_tool`

注意：环境探测只能说明路径可能存在，不能证明许可证可用。只有 COMSOL 或
`mphserver` 成功接受真实操作后，才能认为许可证链路可用。

## MCP Tools

- `comsol_detect_tool`
- `comsol_start_bridge_tool`
- `comsol_bridge_status_tool`
- `comsol_stop_bridge_tool`
- `comsol_bridge_ping_tool`
- `comsol_mphserver_status_tool`
- `comsol_start_mphserver_tool`
- `comsol_stop_mphserver_tool`
- `comsol_connect_tool`
- `comsol_new_model_tool`
- `comsol_open_model_tool`
- `comsol_save_model_tool`
- `comsol_model_info_tool`
- `comsol_list_parameters_tool`
- `comsol_set_parameter_tool`
- `comsol_list_studies_tool`
- `comsol_run_study_tool`
- `comsol_evaluate_tool`
- `comsol_export_plot_tool`
- `comsol_export_table_tool`

## 测试

Python 测试不依赖 COMSOL，只验证环境探测和 bridge 协议：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## 源码管理规则

不要提交 COMSOL 二进制文件、许可证文件、生成的 `.mph` 模型、求解结果、本机
`.env` 或 `comsol_runs/`。

如需执行带检查点的永磁电机 NVH 工作流，请将本 MCP 与仓库中的
[`comsol-motor-nvh-evidence`](../../Skill/comsol/comsol-motor-nvh-evidence/SKILL.md)
Skill 配合使用。该 Skill 增加模型合同、缩减矩阵、Campbell 数据与发布证据门槛，
且不会把专有模型或求解结果纳入仓库。
