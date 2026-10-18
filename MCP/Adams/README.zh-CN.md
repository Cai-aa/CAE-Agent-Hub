# Adams MCP 使用说明

**语言：** [English](README.md) | 中文

本模块从本机已经配置给 Codex 的 Adams MCP 提取，面向 Windows 和用户自行安装的
Hexagon Adams/View 2024.1，包含 16 个工具、3 个资源、配置模板和回归测试。

## 能力

- 探测安装、版本配置、View/Solver/Python 和 localhost Command Server。
- 用项目 manifest 和 CMD 建立箱形刚体、转动副、重力及旋转驱动。
- 运行有超时限制的 View batch，保存请求、日志、验证 JSON、SHA-256 和报告。
- 提取首个关节 FY 的单列数值序列，计算最小值、最大值、均值和 RMS。
- 向用户手动启动的本地 Command Server 发送 query 或前缀允许的 command。

直接 Solver、绘图与动画导出仍未实现；其他 Adams 版本需要重新进行原生测试。

## 安装和 Codex 配置

在本目录使用 Python 3.11 及以上版本：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
```

将 [config.example.toml](config.example.toml) 复制到仓库外，填写本机安装根目录、启动器、
版本和专用工作区。将 [codex-config.example.toml](codex-config.example.toml) 中的命名服务段
合并到 Codex 配置，修改 Python 路径和 `ADAMS_MCP_CONFIG`。其他客户端可参考
[client-config.example.json](client-config.example.json)。模板均为占位路径。

## 推荐流程

1. 调用 `adams_environment_probe` 和 `adams_capabilities`。
2. 需要真实求解时运行 `adams_smoke_test`，它只读取用户安装目录内的四连杆示例。
3. 按 [示例调用参数](examples/project_recipe.json) 创建项目、刚体、关节和驱动。
4. 调用 `adams_simulation_run`，再检查 `adams_evidence_latest` 的原生证据。

`validation.status=VERIFIED` 应结合具体门槛解释。普通 CMD 的成功只能证明批处理完成；
仿真还需要模型验证、真实数值输出和时间范围检查。无关节模型不会自动具备数值结果证明。
当前数值解析支持每行一个标量，不支持通用多列 CSV。

## 执行边界

工作区检查约束输入文件位置，不能限制 CMD 内部所有文件访问；只运行可信脚本。
localhost 和前缀 allowlist 也不是安全沙箱，允许的 live 命令仍可能修改当前模型或写文件。
默认关闭 raw commands。不使用时关闭监听；对外分享前检查日志中的本机路径。
源码不包含虚拟环境、个人配置、许可证、商业手册、安装示例原文和仿真结果。

## 测试与许可

```powershell
$env:PYTHONPATH = (Resolve-Path .\src).Path
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe scripts\protocol_smoke.py
```

测试分为无 Adams 的单元/协议检查和需要合法安装的原生 smoke test，详见
[VALIDATION.md](VALIDATION.md)。桥接源码采用 [MIT](LICENSE)；Adams 本体及相关资料的权利
仍归原权利人所有。
