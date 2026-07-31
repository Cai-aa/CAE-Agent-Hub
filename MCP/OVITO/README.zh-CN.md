# LAMMPS OVITO MCP

该服务通过 MCP 调用本地 LAMMPS 输入文件，并运行明确指定的 OVITO 批处理脚本。
仓库仅包含可复用源码、示例和配置模板；势函数、轨迹、重启文件、求解日志、图片和本机路径不得提交。

## 安装

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -U pip
.\.venv\Scripts\python.exe -m pip install -e .[dev]
Copy-Item .env.example .env
```

在 `.env` 中设置 `LAMMPS_EXE`。需要自动化 OVITO 时，设置 `OVITOS_EXE` 或带有
`ovito` Python 包的 `OVITO_PYTHON`；仅检测到 `OVITO_EXE` 只能说明 GUI 可用。

## 工具

- `lammps_detect_tool`、`lammps_run_input_tool`
- `ovito_detect_tool`、`ovito_run_script_tool`
- `atomistic_job_status_tool`、`atomistic_job_log_tool`、`atomistic_list_jobs_tool`

先检测安装，再调用明确的输入文件或脚本。MCP 作业目录保存 stdout、stderr 和元数据；
LAMMPS 的输出位置仍由输入文件决定，因此应为每个算例使用干净的工作目录。

`examples/in.smoke` 使用 `pair_style zero`，仅验证执行链路，不构成材料模型。
OVITO 的渲染和导出属于后处理证据，不能单独证明上游分子动力学求解完成或物理有效。
