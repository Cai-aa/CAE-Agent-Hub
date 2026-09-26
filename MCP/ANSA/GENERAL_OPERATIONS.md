# Windows 通用 ANSA MCP / General-purpose ANSA MCP 0.5.0

0.5.0 保留 18 个 MCP 工具，具名操作增至 24 项。新增几何、网格质量、材料/载荷/接触、
文件导入导出见 [工程操作与验证边界 / Engineering operations](ENGINEERING_OPERATIONS.md)。

## 中文

默认 18 个通用工具。8 个悬臂梁工具保留用于教学，默认不注册。
教学模式须在 ANSA 与 MCP 两个进程启动前设置 `ANSA_MCP_ENABLE_EXAMPLES=1`。

### 三层操作能力

1. 常用类型化工具：会话、模型统计、实体查询、Card 创建/修改、检查、保存、刷新、历史。
2. `execute_live_ansa_operation`：参数契约见 `get_live_capabilities.general_operations.operations`。
3. `search_live_ansa_api` + `get_live_ansa_api_help` + `execute_live_ansa_python_step`：
   先查询当前版本 API，再编写小步脚本扩展几何、网格、连接、Morph、材料、载荷、边界条件、
   求解 deck 导入/导出。`get_live_entity_fields` 查询现有实体实际 Card 字段，不猜字段名。

| 通用操作 | 参数 | 约束 |
| --- | --- | --- |
| `open_model` | `path`, `replace_current=true` | 允许目录内 ANSA/CAD 文件；替换内存模型，先保存 |
| `set_deck` | `deck_name` | 按实际 constants 探测；切换环境不是转换求解模型 |
| `isolate_entities` | `entity_type`, `entity_ids` | 隔离显示指定实体 |
| `hide_entities` | 同上 | 隐藏指定实体 |
| `delete_entities` | 同上 | force=false、compress=false；回读确认指定 ID 消失 |
| `create_curve` | `points` | 2–200 个 XYZ 点；平滑插值曲线，不是折线 |
| `smooth_solids` | `entity_type="SOLID"`, `entity_ids` | 冻结表皮；不承诺改善质量 |
| `reconstruct_shells` | `entity_type="SHELL"`, `entity_ids` | 使用当前网格设置；先确认设置，再质量检查 |

最多 200 个精确实体 ID，不提供隐式全部模型删除。要求 confirm=true、实时
expected_session_nonce、expected_database、expected_deck 和唯一 operation_id。
检查参数和能力后才进入原生 API。调用开始后异常标为 OUTCOME_UNKNOWN，不能换 ID 重做。
同 ID 的成功重试返回缓存。无通用撤销、强制取消或自动回滚；破坏性操作前保存快照。

每个修改调用在 ANSA 主线程执行、请求重绘并记录 Runtime 历史。小步拆分才能在调用间看到变化；
长脚本和耗时原生 API 内部不保证实时刷新。API 返回、数量变化、网格质量、工程正确性不是同一证据。
任意 Python 非沙箱，有 ANSA 的本机权限，并不受通用文件操作路径限制；不要执行未经审查的代码。
求解器计算、META 后处理、收敛性和工程批准需要各自工作流和证据。

### 第三方安装与升级

外部 MCP Python >=3.10，ANSA 内置 Python >=3.9。安装示例：

```powershell
.\install_ansa_bridge.ps1 -Destination 'D:\ANSAMCP\ansa_plugin' `
  -Workspace 'D:\ANSAMCP\workspace' -ConfigPath 'D:\ANSAMCP\bridge.json'
$env:ANSA_MCP_BRIDGE_CONFIG = 'D:\ANSAMCP\bridge.json'
```

在启动 ANSA 的环境中设置此变量；MCP 客户端 env 也指定同一个绝对配置路径，
并把 ANSA_MCP_WORKSPACE 设为允许工作区。商店版客户端的 LOCALAPPDATA 可能不同。
不分发本机 bridge.json，令牌不包含在插件包中。

```powershell
.\.venv\Scripts\python.exe build_ansa_plugin_package.py --output '.\dist\release-050'
```

省略 --bridge-entry 生成无个人路径的目录/ZIP；增加 --ansa-launcher 指向本机 ansa64.bat，
用官方打包器生成 .bpkg。通过 Development > BETA Packager Installer > Installer 安装到
用户 .BETA 插件目录。为现有电脑保留配置入口可显式增加 --bridge-entry 指向已安装的
ansa_mcp_plugin.py；这种包 manifest 标记 portable_configuration=false，不适合第三方分发。
升级后保存模型、重启 ANSA，从 Plugins > ANSA MCP > Start 启动；同时重启 MCP 服务／重新加载
客户端工具清单。旧进程不会自动从 22 项切换为 18 项。安装本身不启动连接或修改当前模型。

### 跨版本边界

- 默认 .ppl 最低版本为25.0.0，这不是整个25.x系列的兼容证明。
- --minimum-ansa-version 24.0.0 可调整门槛供测试；不能绕过内置 Python >=3.9 要求。
- API 逐项探测，缺失返回 UNSUPPORTED_CAPABILITY；签名差异失败时停止，不静默试其他有副作用的 API。
- 非标准安装路径用 ANSA_HOME/ANSA_EXECUTABLE 指定；不再硬编码 G 盘。
- 其他 ANSA 版本的 GUI、回调和打包器仍需实测。必要时在目标版本上重打包，源代码可移植不等于厂商容器通用。
- 离线 mock/语法测试不等于真实运行验证。未测版本保持待验证。

## English

The default exposes **18 generic MCP tools**, with eight cantilever teaching tools disabled.
Enable examples explicitly with ANSA_MCP_ENABLE_EXAMPLES=1 in both processes before startup.
Use typed tools for common operations, execute_live_ansa_operation for the eight foundational actions above
plus sixteen [engineering operations](ENGINEERING_OPERATIONS.md),
and API search/help plus unrestricted Python steps for broader workflows. Read the connected
version's capability catalog and entity card fields before writing scripts. Symbol presence
does not prove signature compatibility, behavior, mesh quality or engineering validity.

Writes require confirmation, expected session/database/deck and an operation ID. Successful
same-ID requests replay without repeating effects. Post-call exceptions remain OUTCOME_UNKNOWN;
never retry with a fresh ID. Save snapshots first: no generic rollback, undo or force-cancel.
Each mutation requests redraw and records a step; long native calls/scripts cannot provide
frame-by-frame updates. Python is not sandboxed and has ANSA's full local privileges.
Solver execution, META visualization and engineering approval need separate evidence.

External MCP Python >=3.10 and embedded ANSA Python >=3.9 are required. Run install_ansa_bridge.ps1
with your own Destination, Workspace and ConfigPath (example above). Set ANSA_MCP_BRIDGE_CONFIG
to the SAME absolute file in ANSA's launch environment and the MCP client's env; configure
ANSA_MCP_WORKSPACE inside allowed roots. Store-packaged clients may see different LOCALAPPDATA.
Do not distribute credentials or a configured bridge.json.

Omit --bridge-entry when building for redistribution. Add --ansa-launcher for an official .bpkg;
install with Development > BETA Packager Installer > Installer into the user's .BETA directory.
Optional --bridge-entry produces a machine-specific upgrade only. Restart ANSA and the MCP
server/client tool discovery after upgrading; installation does not start the listener.

The descriptor defaults to ANSA25.0.0, not a compatibility certificate. --minimum-ansa-version
allows testing another release but cannot remove the embedded-Python requirement. Missing APIs
fail closed. GUI callbacks, behavior and vendor containers need validation on each release;
rebuild on the target ANSA when necessary. Other versions remain unverified. Nonstandard Windows
installs use ANSA_HOME/ANSA_EXECUTABLE, not hardcoded drive letters.
