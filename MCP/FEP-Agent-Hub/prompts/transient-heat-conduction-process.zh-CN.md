# FEP Agent Hub：真实瞬态热传导过程提示词

你是负责 FEP Agent Hub 的高级 CAE 自动化、传热学与 MCP 工程师。请通过 FreeCAD MCP、Elmer MCP、ParaView MCP 完成一个具有真实物理时间轴的三维瞬态热传导案例，输出时间步结果、过程动画、解析校核和证据链。不得把稳态场的镜头扫描称为瞬态传热。

## 强制原则

1. 正式几何、网格、求解与 ParaView 后处理必须通过三套已注册 MCP 完成。
2. 仅使用白名单 profile `heat_transient_v1` 和结构化参数；禁止任意 shell、任意 Python、原始 SIF 或 `eval` 接口。
3. 所有模型、VTU、日志、图片和证据必须位于配置工作区；公开文件不得写入作者机器绝对路径。
4. 成功必须同时满足原生进程退出码、Elmer 完成标志、20 个真实 VTU、有限温度场、时间序列物理门和 ParaView 帧数。
5. 媒体编码只能处理已验收帧，不能代替求解。

## 环境占位符

- 仓库：`<FEP_AGENT_HUB_REPOSITORY>`
- Python：`<FEP_AGENT_HUB_REPOSITORY>/.venv/Scripts/python.exe`
- 本机软件配置：`<FEP_AGENT_HUB_REPOSITORY>/configs/open-cae.local.toml`
- Codex MCP 配置：`<CODEX_HOME>/config.toml`
- 工作区：从 `[workspace].root` 读取
- 项目：`transient_heat_process_smoke_v1`

所有 FreeCAD、Gmsh、Elmer 和 ParaView 路径必须由 `OPEN_CAE_CONFIG`、环境变量或本机配置解析。

## 模型与物理

- FreeCAD 立方体：10×10×10 mm，语义体 `solid`。
- 网格：三维一阶四面体，目标尺寸 2 mm；输出坐标必须缩放为 SI 的 0..0.01 m。
- 材料：不锈钢冒烟基准，`k=15 W/(m·K)`、`rho=8000 kg/m³`、`cp=500 J/(kg·K)`。
- 初始温度：300 K。
- `x_min`：400 K；`x_max`：300 K；其余表面绝热。
- 时间离散：BDF1，20 个真实时间步，`dt=1 s`，总时长 20 s。
- 每个时间步通过 ResultOutputSolver 输出一个 VTU，文件前缀 `transient_heat`。

## 物理验收

1. 20/20 VTU 文件存在、可读，均含有限 `temperature` 数组。
2. 所有温度始终位于 300..400 K，允许 1 K 数值容差。
3. 跨中温度随时间单调升高，且最终至少比初始温度高 5 K。
4. 采用一维有限板 Fourier 级数计算 20 s 时跨中解析温度，有限元与解析值绝对误差不超过 3 K。
5. PVD 必须包含 1..20 s 共 20 个真实时间值，ParaView 必须验证并导出 20/20 帧。

## MCP 调用顺序

1. FreeCAD：环境探测→文档创建→Box→检查→几何验证→STEP/manifest。
2. Elmer：环境探测→`heat_transient_v1` case→几何导入→SI 网格→ElmerGrid→材料→方程→冷热边界→SIF 生成/校验→真实求解→日志/结果检查。
3. ParaView：启动会话→PVD 打开→中心切片→温度着色→相机→20 帧导出→最终 PNG→中心线 CSV→PVSM→会话停止。
4. 输出中文总结，明确本案例为真实瞬态热传导，而不是稳态镜头效果。

