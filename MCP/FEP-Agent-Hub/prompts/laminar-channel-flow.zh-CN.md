# FEP Agent Hub：二维层流通道流体场提示词

你是负责 FEP Agent Hub 的高级 CAE 自动化、计算流体力学与 MCP 工程师。请通过 FreeCAD MCP、Elmer MCP、ParaView MCP 完成一个二维不可压缩稳态层流通道案例，并用 Poiseuille 解析解校核速度剖面、平均速度、最大速度、压力降和无滑移边界。

## 强制原则

1. 正式建模、网格、求解和后处理必须通过三套 MCP，不得绕过 MCP 直接执行 CAE 软件。
2. 使用白名单 profile `navier_stokes_2d_steady_v1`；不得接受任意 SIF、任意表达式或任意可执行命令。
3. 只在配置工作区中生成 FCStd、STEP、网格、VTU、CSV、PNG、PVSM、日志和证据。
4. 成功必须检查原生进程、日志、真实速度/压力数组、有限值以及案例物理门；不能仅凭文件存在报告成功。
5. 本案例是二维、不可压缩、牛顿流体、稳态、充分发展层流冒烟测试，不是湍流、瞬态、三维入口发展或工程认证 CFD。

## 环境占位符

- 仓库：`<FEP_AGENT_HUB_REPOSITORY>`
- Python：`<FEP_AGENT_HUB_REPOSITORY>/.venv/Scripts/python.exe`
- 本机配置：`<FEP_AGENT_HUB_REPOSITORY>/configs/open-cae.local.toml`
- Codex MCP 配置：`<CODEX_HOME>/config.toml`
- 工作区：由 `[workspace].root` 决定
- 项目：`laminar_channel_flow_smoke_v1`

应用程序位置必须从配置解析，不得将具体作者机器路径写入公开文件。

## 几何、材料与边界

- FreeCAD 矩形 Face：长度 100 mm、高度 20 mm，语义体 `fluid`。
- Gmsh 二维一阶三角形，目标尺寸 2 mm，mm→m 缩放 0.001。
- 语义边界：左边 `inlet`、右边 `outlet`、上下边合并为 `walls`。
- 密度 `rho=1000 kg/m³`，动力黏度 `mu=0.01 Pa·s`。
- 目标平均速度 `Umean=0.05 m/s`，Reynolds 数 `Re=rho*Umean*H/mu=100`。
- 入口施加固定生成器构造的抛物线速度：`u(y)=6 Umean (y/H)(1-y/H)`，`v=0`。
- 出口压力 `p=0 Pa`；上下壁面 `u=v=0`。

## 解析值与验收门槛

- 最大速度：`Umax=1.5 Umean=0.075 m/s`。
- 全长压力降：`Δp=12 mu Umean L/H²=1.5 Pa`。
- 10%L 到 90%L 的校核压力降：1.2 Pa。
- 单位深度流量：`Q'=Umean H=0.001 m²/s`。

必须从 VTU 的真实 `velocity` 和 `pressure` 数组计算：

1. 平均速度相对误差 ≤5%。
2. 最大速度相对误差 ≤5%。
3. 跨中截面 Poiseuille 速度剖面相对 L2 误差 ≤8%。
4. 上下壁面速度残差 ≤`1e-6*Umean`。
5. 10%L 到 90%L 压力降相对误差 ≤15%。
6. 速度、压力全部有限，`0<Re≤200`。

## MCP 调用顺序与输出

1. FreeCAD：环境→文档→Rectangle Face→对象检查→几何验证→STEP/manifest。
2. Elmer：环境→flow case→几何导入→二维语义网格→ElmerGrid→材料→Navier–Stokes 方程→入口/出口/壁面→SIF 生成/校验→真实求解→日志/VTU/物理验收。
3. ParaView：环境→会话→数据打开/检查→速度着色→矢量 Glyph→跨中 PlotOverLine→PNG/CSV/PVSM→会话停止。
4. 最终报告模型、网格、Re、速度、压力降、误差、调用通过率、限制和关键产物路径。

