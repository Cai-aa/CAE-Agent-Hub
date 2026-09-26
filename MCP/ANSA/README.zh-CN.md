# ANSA MCP

[English](README.md)

## 下载 0.5.0

- [第三方 Windows 用户使用的便携插件包](dist/ANSA_MCP_Bridge-0.5.0-release/ANSA_MCP_Bridge-0.5.0.bpkg)
- [原开发工作站指定的本机升级包](dist/ANSA_MCP_Bridge-0.5.0-upgrade/ANSA_MCP_Bridge-0.5.0.bpkg)
- [包的区别、安装与 SHA-256 校验](dist/README.md) · [发布验证说明](RELEASE_0.5.0.md)

首次使用先按下文安装外部 MCP 并生成共享认证配置；只安装插件不会自动配置 MCP 客户端。

### Windows 通用版 0.5.0

默认提供 **18 个通用 MCP 工具**，8 个悬臂梁工具不再默认注册。
具名操作共 24 项，新增几何清理、面/体网格、质量检查修复、材料与实体引用、Abaqus 载荷/约束/壳接触、
Abaqus/Nastran 平铺文件导入导出。见 [工程操作、用法与真实验证范围](ENGINEERING_OPERATIONS.md)。
详见 [通用操作与版本兼容指南](GENERAL_OPERATIONS.md)。这不等于支持所有 ANSA
API 或所有版本：ANSA 内置 Python 要求 >=3.9，外部 MCP Python 要求 >=3.10。

新版原生插件包含连接/会话概览、最近 100 次调用时间线、操作前后数量变化和
脱敏诊断导出。安装/升级及现有 MCP 客户端配置说明见 [插件指南](plugin/README.zh-CN.md)。
升级后保存模型并重启 ANSA，避免 Python 缓存旧 Runtime。统计、API 返回与工程
验证是不同证据；长主线程调用不保证中途刷新界面。诊断不保存任意 Python 源码。

ANSA MCP 是一个面向 BETA CAE Systems ANSA 的本地 FastMCP 服务，采用“外部 Python MCP 进程 + 用户在 ANSA 内手动加载的 Python 桥”架构。除会话查询、模型检查和类型化修改外，它现在也提供**明确确认后在当前 ANSA GUI 进程执行任意 Python**的工具，用于不同仿真任务逐步操作。此工具不是沙箱，拥有 ANSA 进程的本机权限；不要执行未审查的代码。

悬臂梁仅作为可选教学示例保留，以下专用工作流默认关闭。需要时在 ANSA 和 MCP 进程启动前都设置 `ANSA_MCP_ENABLE_EXAMPLES=1`，不建议第三方生产部署启用。

如果要在已打开的 ANSA 窗口内看见悬臂梁处理过程，请使用下面的**可视会话悬臂梁工作流**，而不是独立批处理工具。它在当前 GUI 会话内导入经过固定 SHA-256 校验的网格、缩放并重绘，然后从该会话导出求解文件。桥控制窗显示导入、模型可见、导出、求解和验证阶段。Abaqus/Standard 仍在 ANSA 外部求解；ANSA 窗口不会显示求解器内部迭代或 ODB 云图。

对于其他模型，把 AI 工作流拆成多个 `execute_live_ansa_python_step` 或类型化修改工具调用。每次调用结束，桥在 ANSA GUI 主线程请求 `RedrawAll()`、更新控制窗并记录步骤；`get_live_step_history` 可读取最近 100 步。一次耗时脚本中的内部动作**不会**自动逐帧呈现，外部求解器的迭代和 META 后处理也不会出现在 ANSA 模型视图里。

本机当前开发目标是 ANSA v25.1.2。其他 ANSA 版本是否兼容，必须通过实时探针和实际模型验证；仅检测到安装目录不能证明兼容。

## 架构概览

```text
Codex / 其他 MCP 客户端
          | stdio MCP
          v
外部 `ansa_mcp` FastMCP 进程
          | 双向 HMAC 认证的单行 JSON 协议
          | 仅 127.0.0.1:48762
          v
在 ANSA 内加载的 `ansa_plugin/start_ansa_mcp.py`
          | 保持可见的“ANSA MCP Bridge”控制窗
          | 阻塞式 `BCShow` 维持已加载脚本的生命周期
          | 25 ms GUI `BCTimer` + 非阻塞 socket reactor
          | 具名方法白名单（含显式确认的任意 Python 步骤）
          v
当前 ANSA Python API / 当前数据库
```

两个进程读取同一个 `%LOCALAPPDATA%\ANSAMCP\bridge.json`。其中包含随机令牌、回环地址和允许桥接文件操作访问的根目录。请把该文件视为本机凭据，不要提交到 Git 或发给他人。协议、信任边界和失败状态见 [ARCHITECTURE.md](ARCHITECTURE.md)。

桥还可能写入 `%LOCALAPPDATA%\ANSAMCP\status.json`，但它只是用于诊断的生命周期快照，绝不是权威的存活证据。只有当前通过认证的 `probe_live_bridge.py` 结果或实时 `ping` 才能证明桥正在响应。

该快照会在 bind/timer 初始化后写入 `starting`，只有首个 ANSA 主线程 timer 回调成功后才更新为 `online`；关闭控制窗则写入 `offline`。即使文件显示 `online`，也可能已经过期；仍须用认证 ping，并核对其进程 PID 和回调线程标识是否属于预期 ANSA 会话。

## 安全边界

- 桥接服务只能绑定 `127.0.0.1`，非回环地址会被拒绝。
- Windows 监听 socket 强制使用 `SO_EXCLUSIVEADDRUSE`，绝不启用 Winsock
  `SO_REUSEADDR`，因此桥绑定后，其他本机进程不能共享该端口。即使某进程抢先
  绑定，没有本机凭据也无法冒充桥完成认证。
- 线协议 v3 先发送不含敏感信息的新鲜客户端 nonce；服务端把该 nonce 与自己生成
  的新 challenge 一起绑定到服务端 hello、客户端请求和服务端响应的
  HMAC-SHA-256 证明中。客户端验证服务端后才发送方法和参数，历史 hello 无法重放
  来套取请求；64 位十六进制凭据不会出现在网络消息中。
- 桥只分派具名方法；其中 `execute_python_step` **允许任意 Python**，包括导入模块、访问文件和启动进程。HMAC、会话 CAS、`confirm=true`、操作编号和 64 KiB 代码上限不能约束代码本身的行为；`allowed_roots` 仅约束专用文件工具，不约束任意 Python。只有完全信任 MCP 客户端和将要执行的代码时才启用此工具。
- ANSA 内桥不使用后台 socket worker 或请求队列。GUI `BCTimer` 每 25 ms 调用一次完全非阻塞的 reactor，socket 的 accept、读取、解析、认证、白名单分派和写回都在 ANSA GUI 主线程执行。reactor 最多接纳 32 个活动连接，同时实施 5 秒空闲超时和不可续期的 5 秒“accept 到完整请求”绝对截止时间，请求/响应上限分别为 1 MiB/4 MiB，并使用每 tick 事件数与时间预算。
- 外部客户端对连接后的“client hello → server hello → 请求 → 响应”全过程使用同一个单调时钟绝对截止时间；慢速滴入 hello 或响应字节不能续期。
- recurring timer 由保持可见的 **ANSA MCP Bridge** 控制窗持有。该窗口打开期间，脚本停留在阻塞式 `BCShow` 调用中；关闭窗口会停止 timer 和 bridge，并写入 `offline` 状态。
- 专用保存/导出工具的文件输出受 `allowed_roots` 限制；外部 MCP 还会把数据库保存路径限制在 `ANSA_MCP_WORKSPACE` 内。**任意 Python 工具不受这些路径限制。**桥配置只接受非空的绝对路径列表，格式错误时关闭失败。
- 模型修改工具必须显式传入 `confirm=true`。保存、创建、修改操作还要求调用方生成 `operation_id`，用于幂等控制，并传入实时 `session_nonce` 与预期数据库标识。实体字段更新还要求预期旧值，用于拒绝过期写入。
- FastMCP 会在工具执行前进行严格 JSON 类型校验，桥内还会再次校验；`confirm=1`、`confirm="true"` 等布尔/整数伪装值不会被强制转换，而会直接拒绝。
- 安装器不会创建或覆盖 `ANSA_TRANSL.py`，也不会启动、停止、重启或连接 ANSA。用户必须在目标会话中手动加载桥。

这些机制能降低误操作和远程滥用风险，但它们不是操作系统级沙箱，也不能证明工程正确性。

## 前置条件

- Windows 和本机合法授权的 ANSA 安装。
- 外部 MCP 使用 Python 3.10 或更高版本；它与 ANSA 内嵌 Python 是两个不同运行时。
- Codex 或其他支持 stdio MCP 服务的客户端。
- 有权在目标 ANSA 会话中加载 Python 脚本。

不要在外部虚拟环境中尝试导入 ANSA 内嵌的 `ansa` 包。当前 GUI 会话的 ANSA API 调用由进程内桥执行；固定悬臂梁示例使用 ANSA 官方的独立无界面 Python 模式。

## 1. 安装外部 MCP 服务

在本目录执行：

```powershell
uv sync --extra dev
```

该命令会根据仓库内的锁文件创建 `.venv`。如果本机没有 `uv`，请使用已安装的
Python 3.10+ 启动器创建虚拟环境，再执行
`.\.venv\Scripts\python.exe -m pip install -e ".[dev]"`。

选择一个专用、可写的工作区：

```powershell
$env:ANSA_MCP_WORKSPACE = Join-Path `
  ([Environment]::GetFolderPath('MyDocuments')) 'ANSAMCP\workspace'
$env:PYTHONUTF8 = '1'
```

可选安装提示仅用于发现，不会启动 ANSA：

```powershell
$env:ANSA_HOME = '<ANSA_INSTALL_ROOT>'
$env:ANSA_EXECUTABLE = '<FULL_PATH_TO_ANSA_LAUNCHER>'
```

运行只读环境探针：

```powershell
.\.venv\Scripts\python.exe .\probe_environment.py
```

检测到安装目录、帮助文档或启动器，仅说明这些路径存在，不代表实时会话可达。

## 2. 安装 ANSA 内嵌桥文件

请选择用户拥有的脚本目录。`Destination` 是必填参数，安装器不会猜测应修改哪个 ANSA 安装目录或启动目录。

```powershell
$pluginDirectory = Join-Path `
  ([Environment]::GetFolderPath('MyDocuments')) 'ANSAMCP\ansa_plugin'

.\install_ansa_bridge.ps1 `
  -Destination $pluginDirectory `
  -Workspace $env:ANSA_MCP_WORKSPACE
```

安装器会：

1. 把 [`ansa_plugin`](ansa_plugin) 内容复制到指定目录；
2. 生成 `%LOCALAPPDATA%\ANSAMCP\bridge.json`，内含随机令牌，默认端口为 `48762`；
3. 按需创建允许的工作区；
4. 输出需要手动加载的 `start_ansa_mcp.py` 完整路径。

安装器还会在脚本目录写入不含令牌的 `bridge_config_path.txt`。ANSA 启动脚本优先读取该绝对路径，再把它传给进程内桥；这样 ANSA 和打包版 Codex 即使看到不同的 `LOCALAPPDATA`，也使用同一份配置。重新运行安装器会保留有效的现有令牌；请勿手工复制或公开配置中的令牌。

安装器不会修改 ANSA 启动钩子，尤其不会覆盖已有 `ANSA_TRANSL.py`；同时兼容 Windows PowerShell 5.1 与 PowerShell 7。

## 3. 在目标 ANSA 会话中加载桥

请自行打开目标 ANSA GUI。使用 ANSA 正常的脚本加载功能，手动执行已安装的 `start_ansa_mcp.py`。这一显式步骤用于避免安装器把桥注入每一个 ANSA 会话。

ANSA 会打开一个小型 **ANSA MCP Bridge** 控制窗。在需要 MCP 访问期间必须保持该窗口打开。`BCShow` 会有意让 Load Script 调用保持活动，使 ANSA GUI 事件循环能够驱动 recurring `BCTimer`。关闭控制窗是正常的本地停止方式：它会停止 timer、关闭监听 socket 和活动连接、写入 `offline`，然后让已加载脚本返回。

### 推荐：一次安装的 Plugins 页入口（v0.5.0）

使用 `build_ansa_plugin_package.py` 为已安装的桥接生成新版 `.bpkg`。在
**Development > BETA Packager Installer > Installer** 中安装，位置选择
**Your .BETA plugins directory**；重启后在 **Plugins > ANSA MCP** 使用按钮。
详见 [插件安装说明](plugin/README.zh-CN.md)。插件入口自动加载，服务由 Start 启动。

```powershell
.\.venv\Scripts\python.exe .\build_ansa_plugin_package.py `
  --output '.\dist\ANSA_MCP_Bridge-0.5.0-build' `
  --ansa-launcher '<ANSA_INSTALL_ROOT>\ansa64.bat'
```

请把 `<ANSA_INSTALL_ROOT>` 替换为自己的 ANSA 安装目录。不传 `--bridge-entry`
生成便携包；用 `ANSA_MCP_BRIDGE_CONFIG` 让两个进程指向同一份现有配置。
构建不会安装到用户 ANSA 配置。v0.5.0 继承元数据生命周期修复，并在包内携带
监控 Runtime。官方安装、新进程插件 Start、真实认证调用、数量差值和原生控件
回调已在本机 ANSA v25.1.2 的隔离配置验证。用户实际桌面安装仍需重启后确认。

### 备选：不经过 Plugin Manager 的 Start/Status/Stop 按钮

在 ANSA 中使用 **Development > Load Script** 加载已安装的 `ansa_mcp_controls.py`。加载时只注册三个用户脚本按钮，不会启动桥，也不会修改当前模型。按钮位于 **Custom > Scripts** 的 **ANSA MCP** 组。点击 **Start** 会打开桥状态窗，并请求把它停靠在 **Database** 旁；使用 MCP 时必须保持该窗口打开，关闭它就会停止桥。**Status** 会在消息区打印状态，**Stop** 会关闭桥。有意重启桥后，修改模型前须重新读取认证状态和会话 nonce。

更新 `ansa_mcp_controls.py` 后，在 **Development > Script Manager** 中选中该脚本并执行 **Reload**，再点击按钮；已经注册的旧回调不会因磁盘文件更新而自动替换。如果无法确定加载的是哪个副本，可保存模型后重启 ANSA，再用 **Load Script** 加载已安装目录中的脚本。

旧的单文件 `.ppl` 候选曾导致 `python311.dll+0x1525AD` 访问异常，已停用；不要重新安装 `output/plugin_candidate` 的文件。它使用临时元数据对象，而实测 `session.setPluginInfos` 不增加对象引用计数；直接加载旧桥接入口还触发 ANSA 的 future-import 编译错误。v0.2.0 包分别修复了这两种兼容性问题。旧的本机候选清理脚本不包含在公开发布中；`.ppl.disabled` 仅保留用于回归测试，不可安装。新版通过官方安装器登记。

随后执行：

```powershell
.\.venv\Scripts\python.exe .\probe_live_bridge.py
```

成功结果必须同时包含 `"connected": true`、实时 `ping`、能力和会话响应。仅有配置文件、开放端口或持久化状态文件，都不能证明已经连接到预期的 ANSA 会话。

若控制窗显示 `online`，但探针报 `server authentication failed`，先核对已安装脚本旁的 `bridge_config_path.txt` 指向的配置文件是否与 MCP 客户端的 `ANSA_MCP_BRIDGE_CONFIG` 相同。更新安装文件后，必须在 ANSA 中停止旧桥并重新加载脚本；已运行的桥不会热更新。

## 4. 注册到 Codex

使用同一份配置和同一工作区：

```powershell
.\register_codex_mcp.ps1 `
  -PythonExe "$PWD\.venv\Scripts\python.exe" `
  -Workspace $env:ANSA_MCP_WORKSPACE
```

脚本会先校验桥配置及目标 Python 的 `ansa_mcp` 导入，再修改 Codex。若已存在同名
`ansa` 条目，默认拒绝覆盖；只有明确传入 `-Force` 才会事务式替换，后续任一步骤
失败都会恢复原 Codex 配置。脚本还会持久化 `cwd`、`startup_timeout_sec=30` 和
`tool_timeout_sec=180`；180 秒有意大于桥默认的 125 秒客户端等待。只有确实要
替换当前同名条目时才使用 `-Force`。

也可以按本机路径修改 [`examples/codex_config.example.toml`](examples/codex_config.example.toml)。检查注册结果：

```powershell
codex.cmd mcp get ansa
```

重启 MCP 客户端后，必须先调用 `get_environment` 和 `get_live_bridge_status`，再依赖实时会话。

## 工具清单

前 18 项是默认生产接口；后面的悬臂梁示例须显式启用。

| 工具 | 作用 | 关键约束 |
|---|---|---|
| `get_environment` | 报告安装、工作区和桥状态 | 路径发现仅用于诊断 |
| `get_live_bridge_status` | 对当前桥执行带认证的 ping | 只证明连接 |
| `get_live_capabilities` | 返回已加载桥的精确白名单 | 规划前先调用 |
| `get_live_session_info` | 返回 ANSA/运行时、Deck 和数据库标识 | 写入前必须读取 |
| `get_live_model_summary` | 统计指定当前 Deck 实体类型 | 只读 |
| `list_live_entities` | 分页、限量列出实体 | 精确实体类型和数量上限 |
| `get_live_entity` | 按精确类型和 ID 读取一个实体 | 只读 |
| `run_live_model_checks` | 执行白名单内的 ANSA `Check` 操作 | 保留已有检查历史，但可能更新当前检查结果和 ANSA 内状态；结果必须由工程师复核 |
| `save_live_database` | 在工作区内写出静默 `.ansa` 快照，保持当前活动数据库名称/路径不变 | 会话/数据库 CAS + `operation_id` + `confirm=true`；默认 `overwrite=false` |
| `create_live_entity` | 创建一个明确指定的当前 Deck 实体 | 有界标量字段 + 会话/数据库 CAS + `operation_id` + `confirm=true` + Card 值回读证据 |
| `set_live_entity_card_values` | 修改受限 Card 字段 | 会话/数据库/旧值 CAS + `operation_id` + `confirm=true` |
| `refresh_live_view` | 刷新模型视图 | `confirm=true` |
| `get_live_step_history` | 读取当前桥会话最近 100 条修改步骤、状态及重绘结果 | 只读；进程重启后清空，不是持久审计日志 |
| `execute_live_ansa_python_step` | 在当前 ANSA GUI 主线程执行一段任意 Python，调用结束后请求重绘并记录步骤 | **非沙箱/本机代码执行**；需要当前会话 nonce、数据库、Deck、`operation_id`、`confirm=true`；单次代码 ≤64 KiB |
| `search_live_ansa_api` | 查询已连接 ANSA 的公开 API 名称 | 只读、分页 |
| `get_live_ansa_api_help` | 查询当前版本 API 签名和帮助 | 不执行 API |
| `get_live_entity_fields` | 查询实体可用 Card 字段 | 精确实体类型和 ID |
| `execute_live_ansa_operation` | 八类通用操作 | 会话、数据库、Deck 校验；操作 ID；显式确认 |

### 可选教学工具（默认不注册）

| 工具 | 作用 | 关键约束 |
| --- | --- | --- |
| `prepare_cantilever_static_demo` | 独立 ANSA 批处理会话导入固定三维网格、核对数量、保存 `.ansa` 并导出 Abaqus 输入文件 | `confirm=true`；创建新的工作区算例目录 |
| `solve_cantilever_static_demo` | 用本机 Abaqus/Standard 求解 ANSA 导出的文件 | 精确 `run_id`、`confirm=true`；每个算例仅提交一次 |
| `inspect_cantilever_static_demo` | 读取 ODB 位移与应力，检查支反力平衡 | 精确 `run_id`；要求 `.sta` 成功标记 |
| `stage_visible_cantilever_static_demo` | 为当前 GUI 工作流生成固定输入网格 | 需要新版本在线桥，文件写入共享工作区 |
| `import_visible_cantilever_static_demo` | 在空白 ANSA 会话导入并重绘固定网格 | 会话/数据库 CAS、固定 SHA-256、`operation_id`、`confirm=true`；拒绝非空模型 |
| `export_visible_cantilever_static_demo` | 从同一 ANSA GUI 会话保存快照并导出求解 deck | 同一运行 ID 和桥会话、数量检查、不得覆盖现有文件 |
| `solve_visible_cantilever_static_demo` | 保持 ANSA 模型可见，向 Abaqus/Standard 提交 GUI 导出的 deck | 桥控制窗显示求解阶段；求解器是独立进程 |
| `inspect_visible_cantilever_static_demo` | 读取 ODB 并检查位移、应力、支反力 | 桥控制窗显示验证阶段；不代替工程复核 |

### 任意任务的逐步可视操作

1. 在目标 ANSA 窗口加载最新版桥并保持控制窗打开；`get_live_bridge_status` 必须显示实时认证连接。
2. 用 `get_live_session_info` 读取当前 `database`、`session_nonce`、`deck`。每个修改步骤调用一个类型化工具或 `execute_live_ansa_python_step`；任意 Python 工具还要提供简短 `step_name`、代码、唯一 `operation_id` 和 `confirm=true`。
3. 每次调用返回的 `live_step.sequence`、`status`、`view_refresh` 是“桥请求了 ANSA 重绘”的证据；桥控制窗显示最近一步。让每个调用只做一个便于观察和回读的操作，调用返回后再执行下一步。使用 `get_live_model_summary`、`get_live_entity` 或任务专属检查验证模型确实发生了预期变化。
4. 若 `view_refresh.returned_success=false`，不能声称该步已在画面中可见；先检查 ANSA 窗口和模型状态。若出现 `OUTCOME_UNKNOWN`，保留原 `operation_id`，先读回状态，绝不换 ID 盲目重试。

任意 Python 的 `execution_returned=true` 只证明脚本正常返回，`model_effect_verified=false` 表示桥无法自动证明任意代码的工程语义。当前实现只能在**每次 MCP 调用后**给 GUI 重绘机会；一次脚本中的连续建模循环、阻塞 ANSA API 或外部求解器不会自动生成逐帧画面。对于外部求解和后处理，仍需相应求解器/META 的接口及独立证据。

### 固定悬臂梁算例

该算例为 200 × 20 × 10 mm 的钢制实体梁：615 节点、320 个 C3D8I 六面体单元，弹性模量 210000 MPa、泊松比 0.3；x=0 端固定，x=200 端面均布向下合计 100 N。单位为 mm、N、MPa。ANSA v25.1.2 在独立批处理进程中导入、核查、保存并导出模型，随后由本机 Abaqus/Standard 求解。它不修改当前打开的 ANSA GUI 数据库，也不依赖 GUI 桥在线。

#### 在 ANSA 窗口中可视化执行同一固定算例

先在 ANSA 中打开**新空白模型**，按第 3 节加载**更新后的** `start_ansa_mcp.py`，保持桥控制窗打开。本工作流拒绝已有节点、单元、材料、属性或几何的模型，不会清空或覆盖用户数据库。外部 MCP 的 `ANSA_MCP_WORKSPACE` 必须位于桥配置的 `allowed_roots` 中。先运行 `probe_live_bridge.py`，核对认证连接、ANSA 进程 ID、会话 nonce，以及 `get_live_capabilities.methods` 中存在 `import_fixed_cantilever`。

通过 stdio MCP 分阶段运行：

```powershell
$env:ANSA_MCP_WORKSPACE = Join-Path `
  ([Environment]::GetFolderPath('MyDocuments')) 'ANSAMCP\workspace'
.\.venv\Scripts\python.exe .\examples\run_visible_cantilever_demo.py
```

示例依次调用会话查询、固定网格准备、GUI 导入、GUI 导出、Abaqus 求解和 ODB 检查。导入后模型会在 ANSA 当前窗口缩放并重绘；求解时输入模型保持可见，桥控制窗给出阶段提示。写操作响应不确定时，不要换 `operation_id` 盲目重试，先检查 ANSA 实时模型和输出文件。桥关闭后后续阶段会拒绝；若用户在导入与导出之间修改模型，数量变化会被拒绝，卡片或载荷等数值变化仍须检查导出文件及最终求解证据。

固定悬臂梁仍是唯一内置端到端算例；其他任务可以通过通用 Python 步骤调用在 GUI 中逐步操作，但模型构建、求解器输入、求解提交、后处理及工程验证必须针对实际任务编排，不能由“可重绘”自动推断完成。

在本项目目录可通过 stdio MCP 依次调用这三个工具：

```powershell
.\.venv\Scripts\python.exe .\examples\run_cantilever_demo.py
```

可用 `ANSA_MCP_WORKSPACE` 指定专用可写工作区。每次运行产生唯一的 `cantilever_demo/<run_id>`，保留源文件、ANSA 导出文件、`.ansa`、求解日志、`.sta`、`.odb`、`results.json` 和 `verification.json`。若已求解的任务中断，可仅复核现有结果，避免重复提交：

```powershell
.\.venv\Scripts\python.exe .\examples\run_cantilever_demo.py --inspect <run_id>
```

梁理论的自由端位移参考值为 0.7619 mm。ANSA 导入数量、导出关键字、求解成功标记、ODB 数据与 100 N 支反力平衡都有独立验证；但工程使用仍需复核网格、材料、边界条件、应力分布、求解日志与网格敏感性。

`get_live_capabilities` 会返回精确的桥方法、模型检查、默认摘要实体类型、数量上限以及实体/Card 校验策略。实体类型和 Card 字段还会在每次调用时由当前 ANSA Deck 校验，它们不是跨 Deck 的静态白名单。任意 Python 工具虽可调用 ANSA API，但 API 在当前版本/Deck 中是否有效仍须实际验证。
写操作的 `operation_id` 必须为 8-128 个字符，只能使用字母、数字、`_`、`.`、`:` 或 `-`。处理结果不确定的重试时应复用同一 ID，不要通过新建 ID 掩盖未知结果。桥会在 ANSA 变更开始前把 ID 记为 `pending`；类型化工具完成专用回读、任意 Python 脚本正常返回后才改为 `success`（后者**不**证明模型语义正确）。同一 ID 与相同参数的成功重试会返回已记录结果；重放 `pending` ID 会返回 `OUTCOME_UNKNOWN`，且不会再次变更模型；换参数复用会被拒绝。当前会话的账本最多保存 256 条 pending/success 记录；容量耗尽时会在变更前拒绝新写入，不会驱逐旧的安全记录。

外部客户端调用桥的超时必须严格大于桥配置中的
`request_timeout_seconds`，并为响应传输预留额外余量。如果客户端超时过短，
可能在 ANSA 仍在执行时就停止等待。若写操作可能已经开始但没有观察到经验证的响应，
外部客户端会抛出 `OUTCOME_UNKNOWN`：先检查实时状态；确需重试时复用原来的 `operation_id`，绝不能换一个新 ID 盲目重试。已断开的原调用无法再收到后续响应；但只要当前会话账本仍把该操作记为 `pending`，同 ID 重试就会收到桥返回的 `OUTCOME_UNKNOWN`，且不会重复变更。

`run_live_model_checks` 会执行白名单内的 ANSA `Check` API。它会保留已有的
检查历史，但可能更新当前检查结果及相关 ANSA/UI 状态，因此它是“带状态影响
的诊断操作”，不能当作纯只读调用。

## 推荐操作顺序

1. 调用 `get_environment`。
2. 确认 `get_live_bridge_status.connected == true`。
3. 读取 `get_live_capabilities` 和 `get_live_session_info`，保留返回的 `session_nonce` 与数据库标识。
4. 通过模型摘要和精确实体读取检查当前模型。
5. 执行适用的模型检查，并保留机器可读输出。该操作会保留已有检查历史，
   但可能更新当前检查结果，因此应按 ANSA 检查/状态操作处理。
6. 写入前重新读取当前数据库和目标实体。
7. 传入返回的会话 nonce、数据库标识以及（修改时）旧字段值，生成唯一 `operation_id`，再以 `confirm=true` 明确批准写入。
8. 修改后重新读取实体，并重复相关检查。
9. 仅把数据库保存为工作区内的新相对 `.ansa` 快照，并独立复核。桥使用静默 `SaveAs`，成功后保持当前活动数据库名称/路径不变；只有用户明确传入 `overwrite=true` 才允许覆盖已有目标。

## 为什么不默认使用官方 IAP / `-listenport`

ANSA 自带 Remote Control/IAP 客户端，也可以用监听端口方式启动。该接口适合受信任的自动化，但其脚本执行模型可以接受任意 Python 文本或文件，且没有本项目的“challenge 绑定双向 HMAC + 细粒度方法白名单”。只有使用 `-listenport <port>` 启动（或重启）的 ANSA 进程才能被连接；不谨慎使用客户端默认动作还可能重置数据库或停止监听。未来若增加 IAP 后端，必须在 IAP 前增加仅回环可达的认证/授权前置层，而不能直接暴露原始脚本执行。

因此，本项目只把官方客户端检测结果作为诊断信息，并明确返回 `official_iap_enabled=false`。默认后端是本机、带认证、类型化的桥。若要改为原始远程脚本执行，必须另行进行威胁评审并取得用户明确授权。

## 验证方法与证据边界

离线检查：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe .\stdio_smoke.py
```

`pytest` 和 `stdio_smoke.py` 只能验证 Python 逻辑、Schema 与 MCP stdio 握手。它们不会启动 ANSA、不会消耗 ANSA 许可证，也不能证明内嵌 API、桥连接、模型检查、网格或求解器 Deck 真实可用。

实时连接证据必须在同一次验证中满足：

1. 预期 ANSA GUI 会话处于打开状态；
2. 桥脚本已在该会话中加载，且 **ANSA MCP Bridge** 控制窗保持打开；
3. `probe_live_bridge.py` 返回通过认证的实时响应；
4. MCP 实时工具返回相互一致的会话和数据库信息。

工程验证还必须由合格 CAE 工程师针对具体模型复核几何、网格、属性、连接、载荷/约束、求解器卡片及求解结果。本 MCP 不能独立承诺工程适用性。

桥在阻塞式 `BCShow` 调用中保持 **ANSA MCP Bridge** 控制窗可见，并由该窗口的 GUI `BCTimer` 每 25 ms 运行一次 socket reactor。监听 socket 和每个已接受 socket 都为非阻塞；accept、读取、解析、认证、白名单分派、响应序列化和写回全部在 ANSA GUI 主线程执行。reactor 最多保持 32 个活动连接，连接空闲 5 秒或从 accept 起 5 秒仍未收到完整请求时关闭，请求/响应上限分别为 1 MiB/4 MiB，并遵守每 tick 的事件数与时间预算（最多 4 个完整请求或约 10 ms 的分派工作）。关闭控制窗或调用 `stop` 时，会先停止 timer，再关闭监听 socket 和所有活动 socket、写入 `offline`，最后让 `BCShow` 返回。

这个可见生命周期来自 ANSA v25.1.2 的 GUITK 官方约束。其 `BCWindowCreate` 文档明确说明：脚本结束时，`BCOnExitHide` 不会保留窗口，窗口会按 `BCOnExitDestroy` 的效果销毁；官方 timer 示例也把 `BCTimer` 挂在窗口下，并通过 `BCShow` 保持脚本运行。因此，从未显示的隐藏窗口不能在 Load Script 返回后继续作为常驻宿主。`BCTimerSingleShot` 适合延迟执行回调，但 ANSA 并未承诺“自重排的 single-shot 回调”可跨脚本返回长期存活，本桥不依赖这种行为。先 `BCShow` 再隐藏窗口也不能解决问题：一旦 show 调用返回，脚本即可结束，同一销毁规则仍然生效。

这些传输层限制满足了 ANSA 主线程要求，但不能把同步的 ANSA C/API 调用变成非阻塞操作。大规模实体收集、模型检查和保存仍可能在 ANSA 返回前冻结 GUI。如果写操作可能已经开始后客户端超时，客户端必须将其视为 `OUTCOME_UNKNOWN`；已断开的原调用无法再收到后续响应。应先检查实时状态，并在适当时复用同一个 `operation_id`：桥会重放已验证成功的结果，或针对仍为 `pending` 的记录返回 `OUTCOME_UNKNOWN` 而不重复变更。不要创建新 ID 重试。

## 常见问题

- **`bridge config not found`**：运行 `install_ansa_bridge.ps1`，或把 `ANSA_MCP_BRIDGE_CONFIG` 指向已生成配置。
- **连接被拒绝**：桥尚未加载、控制窗已经关闭、加载在另一个会话、已经退出，或两个进程使用了不同配置/端口。不要因此自动重启或终止 ANSA。
- **`status.json` 显示正在运行，但探针失败**：该文件是可能过期的诊断历史。只信任当前通过认证的探针/`ping`；只有在核对目标 ANSA 会话后才考虑重新加载或停止桥。
- **认证失败**：确保外部服务和 ANSA 内桥读取的是同一配置路径。已安装脚本旁的 `bridge_config_path.txt` 会固定 ANSA 使用的路径；对同一配置重新运行安装器会保留有效的旧令牌。
- **路径被拒绝**：使用 `ANSA_MCP_WORKSPACE` 内的相对保存路径，不要仅为绕过错误而扩大 `allowed_roots`。
- **数据库或旧值过期**：其他操作已经改变会话。重新读取会话和实体状态，再判断是否仍应修改。
- **ANSA API、实体类型或字段被拒绝**：读取实时能力和实体。名称会随当前 Deck 和 ANSA 版本变化，不要猜测 Card 字段。

## 开发入口

- `python -m ansa_mcp`：安装后/虚拟环境内的 stdio 服务入口。
- `python server.py`：源码检出目录下的便捷入口。
- `probe_environment.py`：只读配置和路径诊断。
- `probe_live_bridge.py`：带认证的只读实时桥探针。
- `stdio_smoke.py`：外部 MCP stdio 冒烟测试，不代表 ANSA 实时验证。
