# 楞次定律瞬态涡流耦合电磁场验证报告

## 1. 结论

FEP Agent Hub 已新增并验证 `magnetodynamics_2d_transient_eddy_v1` 白名单分析能力。正式验证由 FreeCAD、Elmer FEM、ParaView 三个独立 MCP Server 依次执行，最终状态为 **PASS**：

- 主仿真流程 95 次 MCP 调用，95/95 返回 `SUCCEEDED`；电场专项 ParaView 补充流程 11/11 成功；本案例合计 106/106；
- 基线工况 40/40 个 Elmer BDF1 原生时间步有效；
- 半时间步工况 80/80 个原生时间步有效；
- 加密网格工况 40/40 个原生时间步有效；
- 四个三角波斜坡的楞次增量符号门禁全部通过；
- 感应电流方向完成反转，焦耳耗散有限、非负且非零；
- 时间步和网格敏感性均低于预设门槛；
- ParaView 识别 40 个真实物理时间值并导出 40 帧，不是单场插值伪动画。

本案例是二维平面 `Az` 瞬态涡流冒烟验证，不是完整三维线圈、电机或感应加热器设计。这里的“电场”是由 `E_z=-∂Az/∂t` 得到的感应电场，不是静电标势场。

## 2. 提示词与执行逻辑

正式提示词保存在 `prompts/lenz-law-transient-eddy-current.zh-CN.md`。执行链为：

1. FreeCAD MCP 创建空气域、铜导体和一对正负线圈截面，执行布尔切割、对象检查、几何有效性检查，并导出 FCStd、STEP 和语义清单。
2. Elmer MCP 用固定 profile 生成四分区共节点 Gmsh 网格，再由 ElmerGrid 转换并核验 SI 坐标和 Physical IDs。
3. Elmer MCP 设置空气、铜和非导电等效线圈材料，设置固定四斜坡电流密度表、外边界 `Az=0`、BDF1 时间积分和真实 VTU 逐步输出。
4. ElmerSolver 求解总磁矢势 `Az`；后处理由相邻原生时间步确定 `E_z`、`Jeddy,z=σE_z` 和 `q=J²/σ`，没有向铜导体施加源电流。
5. 自动门禁检查进程、日志、文件数量、有限值、涡流、焦耳能量、楞次符号和方向反转。
6. ParaView MCP 打开 PVD 时间集，检查字段和时间值，导出云图、方向 glyph、中心线 CSV、PVSM 和 40 帧 PNG。
7. 基线、半时间步和加密网格结果进行误差复核，最后形成报告和综合视频。

## 3. 模型、材料与离散

| 项目 | 数值 |
|---|---:|
| 空气域 | 160 mm × 120 mm |
| 中央铜导体 | 40 mm × 30 mm |
| 左/右线圈截面 | 各 8 mm × 40 mm |
| 等效叠厚 | 20 mm |
| 铜电导率 | 5.8×10⁷ S/m |
| 相对磁导率 | 全部为 1 |
| 峰值线圈电流密度 | ±1.0×10⁶ A/m² |
| 波形 | 0 → +峰值 → 0 → −峰值 → 0 |
| 总物理时间 | 20 ms |

| 工况 | 全局网格 | 节点 | 二维单元 | 边界单元 | 时间步 |
|---|---:|---:|---:|---:|---:|
| 基线 | 2.0 mm | 5,760 | 11,238 | 280 | 40 × 0.5 ms |
| 时间加密 | 2.0 mm | 5,760 | 11,238 | 280 | 80 × 0.25 ms |
| 网格加密 | 1.5 mm | 10,725 | 21,074 | 374 | 40 × 0.5 ms |

## 4. 字段定义与真实性边界

- Elmer 原生未知量：总磁矢势 `Az(t)`。
- 磁感应强度：`B=(∂Az/∂y, -∂Az/∂x)`；报告同时保留 Elmer BSolver 的 `B` 字段。
- 铜中感应电场：`E_z(t_n)=-(Az_n-Az_{n-1})/Δt`。
- 铜中涡流密度：`Jeddy,z=σE_z`；空气与等效线圈的该派生涡流值保持为零。
- 焦耳功率密度：`q=Jeddy,z²/σ`，只在铜区积分。
- 诊断磁矩：`m_y=-½∫x J_z dV`。它是二维等效截面的楞次符号代理量，不是额外求解自由度。

VTU 中的 `E_z`、`Jeddy`、焦耳密度与诊断磁矩是从 Elmer 原生 `Az` 时间步确定性派生的字段；ParaView 插值和视频转场不能作为物理验收证据。

## 5. 楞次定律门禁与磁扩散滞后

铜导体在三角波转折后保留上一个斜坡的扩散场。因此，若直接用“总感应磁矩 × 当前外源变化率”在斜坡中点判定，会把真实的磁扩散记忆误判为违反楞次定律。

本验证对每个斜坡使用其起点总磁矩作为残余基线：

`Δm_induced(t)=m_induced(t)-m_induced(t_ramp_start)`

并要求四个斜坡中点均满足：

`Δm_induced × dm_external/dt < 0`

四段门禁均为 PASS。与此同时，总感应磁矩完成对抗方向的延迟被独立保留：

| 斜坡 | 总磁矩进入对抗方向的延迟 |
|---|---:|
| 0 → +峰值 | 0.5 ms |
| +峰值 → 0 | 2.5 ms |
| 0 → −峰值 | 0.5 ms |
| −峰值 → 0 | 3.0 ms |

所有延迟均短于对应的 5 ms 斜坡。这说明增量响应从斜坡开始即遵循楞次定律，而总量由于铜中的磁扩散需要有限时间完成反转。

## 6. 数值结果与误差

| 工况 | 峰值导体涡流 RMS | 铜中积分焦耳能量 |
|---|---:|---:|
| 基线 | 2.16340×10⁵ A/m² | 1.35093×10⁻⁴ J |
| 时间加密 | 2.18749×10⁵ A/m² | 1.38924×10⁻⁴ J |
| 网格加密 | 2.15425×10⁵ A/m² | 1.34170×10⁻⁴ J |

| 敏感性检查 | 峰值涡流 RMS 差异 | 焦耳能量差异 | 门槛 | 结论 |
|---|---:|---:|---:|---|
| 0.5 ms 对 0.25 ms | 1.101% | 2.757% | ≤ 8% | PASS |
| 2.0 mm 对 1.5 mm | 0.423% | 0.684% | ≤ 10% | PASS |

误差不是与“楞次定律解析真值”的误差，因为该有限空气域、有限导体截面和瞬态扩散问题没有在本报告中假设一个封闭解析解。这里报告的是离散敏感性、场守恒语义、符号关系和耗散正定性。该表不能被表述为工业装置预测误差。

## 7. 稳定性与调用状态

- 正式三工况主流程：95/95 MCP 调用成功；补充感应电场云图与 40 帧流程 11/11 成功；合计 106/106，通过率 100%。
- 三个 Elmer 作业都满足退出码、`Elmer Solver: ALL DONE`、无 fatal 关键字、预期文件数和有限字段门禁。
- 早期开发审计中，求解器虽完成，但旧的“总磁矩瞬时反号”门禁拒绝了第四斜坡。该次未计入正式通过率；门禁经物理审查改为“斜坡增量响应 + 单独报告总量延迟”，同一组原生数据复核通过后才开始正式三工况运行。
- Elmer 日志包含 BSolver 已弃用警告，但没有求解错误。当前安装中 BSolver 已原生运行并输出有效 B 场；后续版本应迁移并回归验证 `MagnetoDynamicsCalcFields`。

## 8. 软件协作状态

| 交接 | 状态 | 证据 |
|---|---|---|
| FreeCAD → Elmer | PASS | STEP、geometry manifest、四个语义体、SI 网格边界一致 |
| Gmsh → ElmerGrid | PASS | Physical Surface/Curve 映射为 Elmer body/boundary IDs |
| Elmer → 派生场检查 | PASS | 40/80/40 个原生 Az 时间步，派生字段有限且铜中非零 |
| Elmer → ParaView | PASS | PVD 暴露 40 个真实时间值，所有必需数组有限 |
| ParaView → 视频 | PASS | 40 帧与 40 个时间值一一对应；后期仅做排版、曲线和标签 |

## 9. 能力边界与后续可能性

当前 profile 可以继续用于线性二维导体板、屏蔽片、简单感应加热截面、线圈距离/电导率/频率敏感性等研究。下列扩展不能直接从本案例宣称已经验证：

- 三维闭合涡流路径和线圈端部效应；
- 铁磁芯非线性、饱和、磁滞和叠片损耗；
- 运动导体、洛伦兹力与结构耦合；
- 温升反作用于电导率的电磁—热双向耦合；
- 工业级线圈阻抗、功率、电磁兼容或效率预测。

## 10. 证据与产物

工作区项目名：`lenz_eddy_current_smoke_v1`。关键相对路径如下：

- `geometry/model.FCStd`、`geometry/model.step`、`geometry/geometry_manifest.json`
- `mesh/model.geo`、`mesh/mesh_manifest.json`、`mesh/semantic_map.json`
- `solver/case.sif`、`solver/solver.log`、`solver/case_model.json`
- `results/lenz_baseline.pvd`、`results/lenz_baseline_t0001.vtu` … `t0040.vtu`
- `post/lenz_time_history.csv`
- `post/lenz_eddy_current_final.png`
- `post/lenz_magnetic_flux_density.png`
- `post/lenz_electric_field_z.png`
- `post/lenz_eddy_direction_glyphs.png`
- `post/lenz_conductor_centerline.csv`
- `post/lenz_transient_state.pvsm`
- `post/lenz_validation_summary.json`
- `evidence/mcp_lenz_eddy_trace.json`

公开仓库只保存代码、提示词、精简指标和报告；大型原始仿真文件继续保留在配置的本地工作区中。
