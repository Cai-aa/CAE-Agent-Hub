# FEP Agent Hub 二维谐波变压器电磁感应验证报告

## 1. 结论

本次扩展与真实冒烟案例结论为 **PASS**。FreeCAD、Gmsh/ElmerGrid、
ElmerSolver、ParaView 均通过各自独立的 STDIO MCP Server 被实际调用，最终
Codex 全局注册也已切换到本仓库。正式电磁链共记录 111 次工具调用，
`111/111 SUCCEEDED`；不存在把热结果、手写 CSV 或伪造 VTU 作为电磁证据的情况。

这里的 PASS 只表示固定的线性二维开路变压器效应案例及已声明 MCP 契约通过，
不表示工业变压器设计精度，也不代表任意未来 CAE 案例均已验证。

## 2. 仿真目的与模型边界

案例验证以下链路：初级交流安匝产生磁场，高磁导率三柱铁芯集中并闭合磁通，
开路次级位置由同一有限元磁通计算出非零感应电压；随后用半电流与加密网格检查
线性和数值敏感性。

模型为 50 Hz、二维平面、20 mm 等效叠厚、线性无损铁芯、均匀化绞线区域和
开路次级。未建模磁饱和、磁滞、叠片涡流、铜损/集肤效应、负载功率、效率、
温升和三维端部漏磁。

## 3. 软件与 MCP 清单

| 项目 | 实测版本/数量 |
|---|---:|
| FreeCAD | 1.1.3 |
| Gmsh | 4.15.0 |
| ElmerSolver | 26.2-devel |
| ParaView | 6.2.0-RC1 |
| FreeCAD MCP | 15 tools，1 resource，1 template |
| Elmer MCP | 17 tools，1 resource，3 templates |
| ParaView MCP | 17 tools，1 resource，2 templates |
| 合计 | 49 tools |

扩展前 Elmer MCP 仅支持 `heat_steady_v1`；本次新增白名单 profile
`magnetodynamics_2d_harmonic_v1`，同时保留原热传导生成器和结果门禁。

## 4. 几何与语义

FreeCAD 中以 mm 建立共面的二维 Face，经固定 Runner 执行融合与切割。空气域为
160 mm × 140 mm；铁芯由上轭、下轭、左柱、中柱、右柱五个矩形融合。初级与
次级各由左右两个 5 mm × 30 mm 均匀化截面表示。

| semantic_id | Gmsh Physical Surface | Elmer Body ID |
|---|---:|---:|
| `air` | 1 | 1 |
| `core` | 2 | 2 |
| `primary_pos` | 3 | 3 |
| `primary_neg` | 4 | 4 |
| `secondary_pos` | 5 | 5 |
| `secondary_neg` | 6 | 6 |
| `outer_boundary` | 1001 | Boundary 1（ElmerGrid 重编号） |

`geometry_manifest.json` 保存每个最终区域的 `semantic_id`、包围盒、面积以及构造
矩形指纹；Gmsh 生成无重叠共节点分区。Elmer 网格坐标范围为
`[-0.08, 0.08] × [-0.07, 0.07] m`，确认完成 mm→m 转换。

## 5. 材料、激励与 SIF

- 频率 50 Hz，角频率 314.159265358979 rad/s。
- 铁芯：相对磁导率 1000，电导率 0 S/m。
- 空气与绕组区域：相对磁导率 1，电导率 0 S/m。
- 初级 100 匝、1 A RMS；正负截面电流密度分别为
  `+666666.6666667` 与 `-666666.6666667 A/m²`，虚部为 0。
- 次级 50 匝、开路、无施加电流密度。
- 外边界复数磁势实部和虚部均为 0。

SIF 使用 `MagnetoDynamics2DHarmonic`、复数 A 势、`BSolver`、
`ResultOutputSolver`。B 场恢复启用材料界面不连续和材料内部平均，避免跨高磁导率
界面进行错误节点平滑。ElmerSolver 从固定相对 SIF 路径启动，解决了 Windows
反斜杠绝对路径触发的 Lua 预扫描噪声。

三个正式工况的进程退出码均为 0，stderr 均为 0 字节，日志均包含
`Elmer Solver: ALL DONE`；大小写敏感检查 `ERROR`、`FATAL`、`Unknown keyword`
均为 0 行。

## 6. 网格与数值结果

| 工况 | I1 (A RMS) | 网格 (mm) | 节点 | 三角形 | 边界单元 |
|---|---:|---:|---:|---:|---:|
| baseline | 1.0 | 1.50 | 12,211 | 24,018 | 402 |
| half_current | 0.5 | 1.50 | 12,211 | 24,018 | 402 |
| fine_mesh | 1.0 | 1.25 | 17,110 | 33,738 | 480 |

| 工况 | Bmin (T) | Bmax (T) | 中柱平均 B (T) | 复磁通 Φ (Wb) | V1 induced (V RMS) | V2 open (V RMS) |
|---|---:|---:|---:|---:|---:|---:|
| baseline | 1.6908e-6 | 1.886822 | 1.144675 | 4.5786634e-4 + j0 | 14.38430 | 7.19215 |
| half_current | 8.4259e-7 | 0.943411 | 0.572338 | 2.2893317e-4 + j0 | 7.19215 | 3.59607 |
| fine_mesh | 7.8645e-8 | 1.892344 | 1.145771 | 4.5830450e-4 + j0 | 14.39806 | 7.19903 |

基线铁芯平均 B 与远场空气平均 B 的比值为 3573.66，证明磁通主要集中于铁芯。
A 势差和 B 线积分所得磁通的相对差为 `1.42e-6`。三工况均包含有限、非零的
`a re/a im/b re/b im` 真正 VTU 数组。

`V2/V1=0.5` 与 `N2/N1=0.5` 一致，但两者来自同一有限元磁通公式，因此它是匝数
关系一致性检查，而不是独立实验验证。V2 是开路感应电压，不表示负载输出功率。

## 7. 线性与网格敏感性

半电流工况相对基线：磁通、Bmax、V2 比值均约为 2；最大线性相对误差为
`1.3992e-8`（远小于 3% 门限），PASS。

1.50 mm 与 1.25 mm 网格比较：

- 中柱磁通相对差：0.0956%；
- Bmax 相对差：0.2918%；
- V2 相对差：0.0956%。

磁通和 V2 均小于 5% 门限，PASS。开发阶段还试算过 1.00 mm 网格，其直角内角
局部 B 峰值达到约 2.099 T，因此没有用放宽阈值的方式强行通过，而是保留失败
证据，并在允许的 1.0–1.5 mm 建议范围内采用 1.25 mm 加密工况。该现象说明尖锐
内角与线性 μr 模型不宜用于工程峰值设计。

## 8. ParaView 后处理

独立 headless 会话打开基线真实 VTU，实测为 `vtkUnstructuredGrid`，72,054 个
输出点、24,420 个单元；A 实/虚部为标量，B 实/虚部为三分量向量，范围均有限。
管线包含 reader、Contour、Glyph 和结构化 ProbeLine。

输出包括 1920×1080 的 B 幅值图、A 等值线图、B 矢量图，201 点中柱采样 CSV，
PVSM 和完整 pipeline inspection。会话由 MCP 正常停止，没有关闭用户手动启动的
ParaView GUI。

## 9. MCP 调用逻辑与协作状态

调用顺序为：

1. 环境、工具、资源和模板清单；
2. FreeCAD 二维区域建模、布尔分区、对象/几何检查、FCStd 与 STEP/manifest；
3. Elmer case、几何导入、Gmsh 物理组、ElmerGrid、SI 网格与语义映射检查；
4. 材料、50 Hz 方程、正负体激励、外边界；
5. SIF 生成/结构验证、ElmerSolver、job/log/VTU/物理门禁；
6. 三工况复算与误差汇总；
7. ParaView 字段检查、云图/等值线/Glyph/ProbeLine、PNG/CSV/PVSM、停止会话。

软件间交接由清单和实际文件双重约束：FreeCAD semantic ID → Gmsh Physical ID →
Elmer Body/Boundary ID → VTU 实际数组 → ParaView proxy/array。没有依赖对象创建顺序
或预先猜测字段名。正式电磁链 `111/111 SUCCEEDED`，协作状态为稳定。

## 10. 回归、覆盖率与正确率口径

- 单元测试：11 passed，1 个原生 CAE opt-in 测试按设计 skipped；已执行项通过率 100%。
- doctor：FreeCAD、Elmer/Gmsh、ParaView 3/3 通过。
- protocol smoke：15 + 17 + 17 = 49 个工具清单通过。
- 全工具契约：49/49 个不同工具覆盖，52/52 次调用契约通过；3 个预期
  `BLOCKED` 分别为无界面 FreeCAD 截图、热 profile 下的电磁激励、稳态动画。
- 热传导 MCP 回归：36/36 调用成功，300/400/350 K 物理门禁通过。
- 电磁正式链：111/111 调用成功，全部物理、线性、网格和 ParaView 门禁通过。

因此“过程/契约通过率”为 100%，“本案例数值正确率”只能表述为全部预定义物理
一致性门禁通过，不能换算成相对真实变压器的 100% 工程精度。

## 11. 修改范围

主要代码修改位于：

- `mcp/freecad/src/freecad_mcp/runner/freecad_runner.py`
- `mcp/freecad/src/freecad_mcp/server.py`
- `mcp/elmer/src/elmer_mcp/mesh.py`
- `mcp/elmer/src/elmer_mcp/sif.py`
- `mcp/elmer/src/elmer_mcp/service.py`
- `mcp/elmer/src/elmer_mcp/server.py`
- `mcp/paraview/src/paraview_mcp/worker/bridge_worker.py`
- `mcp/paraview/src/paraview_mcp/service.py`
- `mcp/paraview/src/paraview_mcp/server.py`
- `scripts/mcp_transformer_smoke.py`
- `scripts/mcp_heat_smoke.py`
- `scripts/mcp_full_validation.py`
- `scripts/protocol_smoke.py`
- `tests/test_mesh_and_sif.py`
- `tests/test_mcp_registry.py`

## 12. 证据和可扩展性

可提交的轻量证据位于 `examples/transformer-induction-2d/`。完整 FCStd、STEP、
Gmsh/Elmer 网格、三套 VTU/SIF/日志、PVSM、调用 trace、job 与哈希只保留在本机
配置的工作区，不进入 Git。

当前白名单能力可合理扩展到其他二维线性开路磁路、C/E/U 型铁芯、简单电磁铁、
电感器和磁传感器位置研究，但几何需能由现有固定二维区域 Runner 表达。非线性
B-H、导体涡流/损耗、负载耦合、运动、电磁力、三维漏磁或多物理温升需要新增独立
profile、结构化参数、参考案例和验收门禁后才能声明支持。
