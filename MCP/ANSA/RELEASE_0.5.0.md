# ANSA MCP 0.5.0 — 2026-09-25

## 交付 / Delivery

- 18 个 MCP 工具不变；通用具名操作由 8 增至 24。新增范围见
  [工程操作说明 / Engineering operations](ENGINEERING_OPERATIONS.md)。
- Runtime 时间线使用具体 operation 名称；修复报告区分执行结束、所选检查通过和工程验证。
- 本机升级包：`dist/ANSA_MCP_Bridge-0.5.0-upgrade/ANSA_MCP_Bridge-0.5.0.bpkg`
  SHA256 `5f96cdefe1e6d96105add33b83d6ca59d53e968d2e8435ed1ce6fca0e4a2bbbb`
- 第三方分发包：`dist/ANSA_MCP_Bridge-0.5.0-release/ANSA_MCP_Bridge-0.5.0.bpkg`
  SHA256 `adc506e425672fa5e0dcc2e3fbb897dfc6bb685304b8875a318415d5db5386eb`
- 两包的 10 个桥运行时模块与源文件 SHA256 一致；仅配置定位包装器有本机/便携差异。
  两包均不携带令牌。未自动安装到用户当前会话。

## 验证 / Validation

- `.venv/Scripts/python.exe -m pytest -q`：**240 passed**，0 skipped，2 个第三方 Authlib 弃用警告。
  包括写入前拒绝、精确实体范围、引用 CAS、原生 API 改写输入字典、修复策略、设置恢复、
  缺失能力、Deck 限制、文件路径/SHA256/外部引用限制、独占导出、回读失败与幂等重放。
- 独立 ANSA 25.1.2 原生测试：`output/engineering_live_06/engineering_report.json`，PID 24016，
  `ok=true`，21 次工程操作，每次成功结果均同 operation_id 重放验证。
  实际生成 16 个平面壳单元、33 个盒体四面体单元；材料、属性材料引用、载荷、约束、接触卡片回读；
  Abaqus 输入/输出和 Nastran 输出/重新输入。
- 畸变网格：长宽比 NASTRAN 阈值 3，检查报告两个失败壳单元；native_fix 后仍失败，
  显式 smooth_shells 后所选检查通过。报告未把原生修复返回值当成质量合格。
- 官方 `.bpkg` 安装、Plugins 启动及真实 GUI 桥：
  `output/engineering_gui_050/gui_report.json`，PID 31120，`ok=true`，36 个记录。
  `output/engineering_gui_050/mcp_engineering_report.json` 记录真实 FastMCP Client → 工具 →
  持久写入客户端 → 认证桥 → 插件创建 MAT1 并回读；同 ID 重放未重复创建。
  同时确认 18 个 MCP 工具、24 个具名操作、面板回调及正常关闭。
- 上述隔离进程均已退出。最后只读查询确认用户会话仍是 PID 23356、原 session_nonce、
  NASTRAN Deck 和 `gear_source.inp.ansa`；没有把工程测试写入该模型。

## 尚未证明 / Not established

- 其他 ANSA 版本、全部网格算法、复杂脏几何自动修复、生产装配与复杂接触模型。
- 重构后模型质量、网格无关性、分析步/约束充分性、求解器收敛、接触方向、工程安全性。
- 输入导出关键字的完全语义无损。通用导入只接收保守限制的平铺 ASCII 文件；
  不包含 INCLUDE 递归、用户子程序和外部文件依赖。
- 节点载荷/约束/壳接触便捷配方首发为 Abaqus；Nastran 提供材料、通用引用和求解文件 I/O，
  不冒充已封装所有 Nastran 载荷/接触类型。
- 原生调用内部逐帧刷新、通用事务回滚或强制中断。

## 升级 / Upgrade

使用 Development → BETA Packager Installer → Installer 安装本机 upgrade 包。
保存模型后重启 ANSA；Plugins → ANSA MCP → Start。重启外部 MCP 服务，查询确认 Runtime 0.5.0
和 24 个具名操作。现有共享认证配置不变；第三方改用 release 包并配置自己的绝对配置路径。

English summary: 18 MCP tools, 24 named operations; 240 automated tests and isolated native/GUI/MCP
validation passed on Windows ANSA 25.1.2 only. New packages have not been installed into the user's
running session. Native completion, selected-check success and engineering approval remain distinct.
The upgrade package is machine-specific; the release package is portable and credential-free.
