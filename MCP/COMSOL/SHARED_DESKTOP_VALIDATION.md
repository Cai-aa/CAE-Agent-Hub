# 共享桌面实测 / Shared Desktop live validation

日期 / Date: 2026-10-25. COMSOL 6.4.0.293, MPh 1.3.1, Windows.

**已验证：同一服务器、同一模型上的 MCP 修改会反映到 COMSOL Desktop 模型树。**

**Verified: real MCP changes on the exact shared server model appear in Desktop Model Builder.**

## 证据 / Evidence

- 本地服务器 `127.0.0.1:2036`，独立进程中的 MPh thin client，`standalone=false`。桌面状态栏回读同一地址。
- 对桌面创建的 `Model1`，通过新启动的真实 MCP stdio 客户端运行两段 API 脚本。桌面从空模型自动出现 `MCP_SHARED_LIVE_DEMO`、组件、几何、固体传热、网格与研究；未重新加载文件。
- 通过现有 MCP Study 工具执行演示稳态求解，得到非空 `sol1`，7481 个解向量项、1 个解，无错误或警告；最高温度 51.6914102071 °C。演示工程已保存。
- 将原 20 W 细网格散热片复制为 `Shared_Heatsink.mph`，在共享 Desktop 中打开后发现真实标签为 `Model2`。API 直接附着该标签，回读 8 域、48 边界、1593279 个解向量项、1 个解和 61.9354073761 °C 的最高温度。
- MCP 修改仅用于显示的根标签 `Shared_Heatsink_LIVE` 和图组标签 `LIVE_SHARED_TEMPERATURE_20W` 后，独立桌面可访问性树即时回读到新根标签；没有重新打开 MPH。主 MCP bridge 保留附着在 `Model2`。
- 新增 MCP 工具的注册、附着与脚本执行通过独立真实 MCP 客户端验证；23 项回归测试全部通过，0 失败、0 跳过。`git diff --check` 在 COMSOL 范围通过。

The live test connected Desktop and a real MPh API client to one server. Two staged scripts created a demo inside Desktop's Model1 and its tree updated without a reload. A real stationary solve completed and evaluated to 51.6914102071 °C. The saved heatsink was then opened in the shared Desktop as Model2, attached directly, and its saved solution evaluated to 61.9354073761 °C. An MCP-only label change appeared in the Desktop tree. All 23 regression tests passed with no skips.

散热片的本次共享验证读取原已求解数据；新增共享求解由小型独立演示完成。此次验证的是可见共享建模与求解能力，未扩展原散热片工程的物理精度结论。

The heatsink verification read its saved solution. The independent small demo verified actual solving through the shared connection. This extends automation visibility, not the engineering validation scope of the heatsink model.

## 修复记录与限制 / Repair history and limits

切换桌面时，保存对话框占用服务器；被其他窗口遮挡时，GUI 点击及原生按钮访问接口未能确认保存。已保留保存工程，结束仅本次任务创建的客户端与专用服务器进程，再使用独立 Desktop configuration/workspace，按“先桌面打开、后 API 附着”顺序重建连接。原独立工程窗口未被结束。

A save dialog blocked a Desktop handoff. After preserving the saved demo, only task-owned clients/server were restarted. Separate Desktop configuration/workspace and Desktop-first startup resolved the handoff. The pre-existing standalone engineering window was preserved.

不要同时向同一服务器启动第二个 GUI。API 树同步不是逐帧动画；需选中相应几何/网格/图组观看。GUI 忙碌可能占用服务器。IPC 超时保护已加入并通过测试；需重载宿主 MCP 才让其原进程采用更新后的保护代码和新增工具注册。当前已有 bridge 工具可继续操作已连接的共享模型。

Avoid starting a second GUI on the same server. Tree synchronization is not frame-by-frame animation; select a geometry, mesh or plot group to view it. GUI activity can temporarily own the server. IPC timeout protection and new registrations require an MCP host reload in the original server process; existing bridge tools already operate the connected shared model.

原始请求、桌面树、模型和测试输出位于被 Git 忽略的 `comsol_runs/shared_desktop/`，包括 `mcp_shared_live_geometry.json`、`mcp_shared_live_physics_mesh.json`、`mcp_live_heatsink_marker.json`、`geometry_desktop_state.json`、`solved_desktop_state.json`、`heatsink_desktop_verified.json`、`live_validation.json`、`unit_tests.log`。认证文件不得提交或展示。

Raw MCP requests, Desktop trees, saved models and tests live in the ignored runtime directory. Authentication files must not be committed or displayed.
