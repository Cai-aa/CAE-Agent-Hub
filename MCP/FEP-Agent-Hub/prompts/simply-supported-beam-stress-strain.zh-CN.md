# FEP Agent Hub：二维简支梁应力—应变冒烟测试提示词

你是负责 FEP Agent Hub 的高级 CAE 自动化、结构有限元和 MCP 工程师。请在保留已有稳态热传导与二维谐波电磁能力的前提下，通过 FreeCAD MCP、Elmer MCP、ParaView MCP 完成一个二维简支梁线弹性应力—应变冒烟测试，并输出可复查的数值、图像、载荷步动画与证据链。

## 1. 强制原则

1. 正式建模、网格、求解和 ParaView 后处理必须通过三套 MCP 完成；不得绕过 MCP 直接调用 CAE 软件。
2. 只允许使用固定、白名单化的 Runner 和结构化参数；不得增加任意 shell、任意 Python、`eval` 或原始 SIF 执行接口。
3. 所有生成物必须位于配置文件指定的 workspace 项目目录内；不得覆盖其他项目。
4. 软件路径必须从 `OPEN_CAE_CONFIG`、环境变量或 `configs/open-cae.local.toml` 解析，不得把作者机器绝对路径写入公开文件。
5. 未经真实求解，不得伪造 FCStd、STEP、网格、VTU、CSV、PNG、PVSM、日志或成功状态。
6. 成功必须同时满足进程退出、日志结束标志、结果文件、有限非零字段和结构物理验收；失败时保留证据并返回 FAILED/BLOCKED。
7. 本案例是二维平面应力线弹性冒烟模型，不是三维接触、塑性、屈曲、疲劳或工程认证分析。
8. 动画采用 10 个真实独立静力载荷级组成的“准静态载荷步序列”，不得称为真实瞬态动力响应。

## 2. 环境和项目

- 仓库：`<FEP_AGENT_HUB_REPOSITORY>`
- Python：`<FEP_AGENT_HUB_REPOSITORY>/.venv/Scripts/python.exe`
- 本机配置：`<FEP_AGENT_HUB_REPOSITORY>/configs/open-cae.local.toml`
- Codex MCP 配置：`<CODEX_HOME>/config.toml`
- 工作区：从本机配置的 `[workspace].root` 读取
- 项目名：`simply_supported_beam_smoke_v1`

执行前读取仓库 `AGENTS.md`、README、架构、安全和测试文档，并确认 Codex 注册的三个 MCP 都指向当前仓库。

## 3. 几何和单位

在 FreeCAD 中按 mm 创建一个矩形平面 Face：

- 长度 `L = 1000 mm`
- 高度 `h = 100 mm`
- 等效出平面厚度 `t = 10 mm`
- 左下角 `(0, 0, 0)`
- 语义体 `beam`

保存 FCStd，验证几何有效、面积为 `100000 mm²`，再导出 STEP 和 `geometry_manifest.json`。网格阶段必须转换成 SI 单位；Elmer 网格范围应约为 `x=0..1 m`、`y=0..0.1 m`。

## 4. 材料、支承和载荷

材料采用各向同性结构钢：

- `youngs_modulus_pa = 210e9`
- `poisson_ratio = 0.3`
- `density_kg_per_m3 = 7850`

采用二维平面应力模型。为确保 Gmsh→ElmerGrid 能稳定保留语义边界，用长度等于一个目标网格尺寸（10 mm）的短支承边近似理想点支承：

- `left_pin`：底边最左 10 mm 短边，`Ux=0`、`Uy=0`
- `right_roller`：底边最右 10 mm 短边，`Uy=0`
- `top_load`：顶边，向下均布压力
- 其余边自由

满载压力：

- `p = 1.0e6 Pa`
- 等效线载荷 `q = p*t = 10000 N/m`
- 总载荷 `P = q*L = 10000 N`
- 理论两端竖向反力各约 `5000 N`

创建 10 个载荷级：`0.1, 0.2, ..., 1.0`。每一级必须重新生成结构化 SIF、通过 SIF 校验、真实运行 ElmerSolver 并检查结果。结果前缀使用 `beam_step_01` 到 `beam_step_10`。

## 5. 网格

1. 使用二维一阶三角形，目标尺寸 `10 mm`。
2. 物理区域和短边边界 ID 必须稳定映射：`beam`、`left_pin`、`right_roller`、`top_load`。
3. ElmerGrid 转换后记录节点、单元、边界单元、坐标范围和 semantic map。
4. 缺失支承点、加载边、SI 转换或唯一语义映射时必须停止。

## 6. Elmer 结构配置

使用白名单 profile：`elasticity_2d_static_v1`。SIF 至少包含：

- `Coordinate System = Cartesian 2D`
- `Simulation Type = Steady State`
- `Procedure = "StressSolve" "StressSolver"`
- `Variable = Displacement`
- `Variable DOFs = 2`
- `Plane Stress = Logical True`
- `Calculate Stresses = Logical True`
- `ResultOutputSolver`
- 结构钢的弹性模量、泊松比和密度
- 左铰、右滚支与顶边压力
- VTU 输出和 Geometry IDs

从 Elmer 的真实位移解按固定平面应力本构推导并写入可审计结果字段：

- `displacement_magnitude`
- `displacement_vector_derived`
- `strain_xx_derived`
- `strain_yy_derived`
- `engineering_shear_strain_xy_derived`
- `max_principal_strain_derived`
- `stress_xx_derived_pa`
- `stress_yy_derived_pa`
- `stress_xy_derived_pa`
- `von_mises_derived_pa`

保留未经派生增强的 Elmer 原始 VTU，禁止用理论值回填有限元字段。

## 7. 理论校核

满载 Euler–Bernoulli 参考值：

- 截面惯性矩 `I = t*h^3/12 = 8.333333e-7 m^4`
- 最大弯矩 `Mmax = q*L^2/8 = 1250 N·m`
- 最大外纤维弯曲应力 `sigma_max = Mmax*(h/2)/I = 75 MPa`
- 最大外纤维应变 `epsilon_max = sigma_max/E ≈ 3.57143e-4`
- 跨中挠度 `delta_max = 5*q*L^4/(384*E*I) ≈ 0.74405 mm`

从 VTU 提取跨中位移、跨中上下外纤维 `|sigma_xx|` 与 `|epsilon_xx|`。考虑二维连续体、点支承离散化和节点平均，三项相对误差目标均为不超过 20%。同时检查：

- 支承自由度残差接近零；
- 位移、应力、应变有限且非零；
- 挠曲方向向下；
- 应力沿梁高呈弯曲拉压分布；
- 不用支承点局部峰值代替跨中理论比较。

## 8. ParaView 和动画

1. 用 10 个真实 VTU 创建 PVD 时间集合，时间值采用载荷系数 `0.1..1.0`。
2. 通过 ParaView MCP 打开 PVD，检查 10 个时间步和实际数组。
3. 用 `displacement_vector_derived` 创建 Warp By Vector，显示放大系数必须在图中标明。
4. 以 `von_mises_derived_pa` 着色，输出 1920×1080 PNG。
5. 导出与 10 个时间步一一对应的 1920×1080 PNG 帧。
6. 输出梁中心线 CSV、PVSM 和 pipeline inspection。
7. 用媒体编码步骤把 MCP 生成帧编码为 MP4；媒体编码不替代任何 CAE 验收。

## 9. MCP 调用顺序

1. FreeCAD：environment probe → session status → document create → rectangle Face → inspect → validate → STEP/manifest export。
2. Elmer：environment probe → case create → geometry import → 2D mesh generate → ElmerGrid convert → mesh inspect → material set → equation/boundary set → SIF generate/validate → solver run → log/result inspect。
3. 对 10 个载荷级重复方程、顶边载荷、SIF 与求解步骤，并保存各级日志。
4. ParaView：environment probe → session start → PVD open/inspect → warp → color → camera fit → image/animation frames/CSV/PVSM/pipeline export → session stop。
5. 回归：pytest → ruff → doctor → protocol smoke → 热案例 → 电磁案例 →完整工具矩阵。

## 10. 最终输出

提交中文报告，至少包含模型、单位、材料、边界、网格统计、10 个载荷级、满载数值、理论误差、日志判据、字段清单、MCP 调用统计、PASS/FAIL、已知局限和所有关键产物路径。只有结构物理门槛与既有热/电磁回归都通过，才能报告案例 PASS。
