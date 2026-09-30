# Maxwell 工具验证记录 / Maxwell tool verification

验证日期：2026-09-30（Asia/Shanghai）。目标：AEDT 2026 R1 / PyAEDT 1.5.0，现有 AEDT 图形会话。

Verified on 2026-09-30 (Asia/Shanghai), against the existing AEDT 2026 R1 session with pinned PyAEDT 1.5.0.

## 离线 / Offline

- `python -m unittest discover -s tests -q`：共 141 项，140 项通过、1 项跳过。跳过的是原有需显式环境开关的 AEDT live unittest；下面的实机验证是独立执行的 MCP 客户端脚本。
- 新增 Maxwell 测试 20 项，涵盖注册和 schema、路由、目标/设计校验、选区、匝数/极性、关联、运动、setup/网格、原生失败、读回、数值结果及 PyAEDT 方法签名。
- Python 编译和作用域内 `git diff --check` 通过；新文件无行尾空格。
- 使用现有 bundled setuptools 成功构建 wheel，并核对包含 `maxwell_capabilities.py`、`maxwell_tools.py` 和 `mcp_server.py`。项目 `.venv` 未安装 setuptools，首次 no-isolation pip 构建因此失败；没有为此安装依赖或修改虚拟环境。

141 offline tests ran: 140 passed and one existing opt-in live test was skipped. All 20 new Maxwell tests passed. Compilation, whitespace checks and wheel-content verification passed. Wheel construction used existing bundled setuptools after the project venv's missing build backend prevented a first no-isolation attempt.

## 实机 / Live

通过 [verify_maxwell_tools.py](scripts/verify_maxwell_tools.py) 的真正 MCP stdio 客户端执行，注册 45 个工具，并实际调用全部 15 个 `maxwell_*` 工具。

Actual MCP stdio client verification registered 45 tools and exercised all 15 dedicated Maxwell tools.

证据 / Evidence:

- [可公开的结构化验证摘要 / Portable verification summary](validation/maxwell2d-2026-09-30.json)
- 摘要记录工具覆盖、原生读回、静磁场数值结果、收敛数据及原始证据的 SHA-256。原始日志、用户路径、进程标识、`.aedt` 工程和求解结果目录保留在本地，不随源代码发布。
- The summary records tool coverage, native readback, numerical output, convergence and raw-evidence hashes. Raw logs, user paths, process identifiers, AEDT projects and solver result directories remain local.
- 使用 [实机验证脚本](scripts/verify_maxwell_tools.py) 和 [工具说明](MAXWELL_TOOLS.md) 在自己的 AEDT 会话中复现 / Reproduce with the live verifier and tool guide in your own AEDT session.

已验证 / Observed:

- Maxwell 2D 磁瞬态：正负极性线圈端子、每端子 10 个导体、1A 绞线绕组；原生绕组节点子名称确认为 `CoilA`、`CoilB`，`association_confirmed=true`。
- 旋转 band：创建 `MotionSetup1`，读回原生 Assignment、运动类型、坐标系、轴和初始位置；`readback_confirmed=true`。几何包围关系仍未验证。
- 平移 band：原生调用返回 `Travel` 运动对象；本版本下该对象的原生属性节点不可用，返回 `readback_confirmed=false`，仅视为 API 调用检查。
- 力/转矩、导体涡流、局部长度网格、瞬态/静磁 setup 创建成功。
- 独立 Maxwell 2D 静磁场算例：原生设计校验通过；新设计由无数据转为求解后有数据，读取数值力结果并创建 `Mag_B` 表面场图。
- profile：`Status: Normal Completion`，`Adaptive Passes converged`。
- 收敛：2 次自适应迭代，240 个三角形；Energy Error 为 0.1724%，Delta Energy 为 0.39796%，均低于 2% 设置目标。
- 原有工程未修改；测试工程保存后关闭，并恢复原活动工程。释放 broker 时保留 AEDT 窗口。

The 2D transient assignment checks confirmed coil polarity/count, winding properties and native terminal membership. Rotation native properties were read back; translation returned an API object but its native property node was unavailable. The separate 2D magnetostatic solve passed design validation, produced numerical data and a magnetic flux-density field plot, completed normally, and converged in two adaptive passes with 240 triangles. Energy error and delta energy were 0.1724% and 0.39796%, below the configured 2% target. The original project was preserved and restored.

## 验证边界 / Limits

没有求解旋转或平移模型；没有进行 3D 实机测试、电机转矩/损耗基准、外部电路耦合、非线性材料校准、网格/时间步独立性研究或工程验收。工具返回的 API 接受、属性读回、场图和既有数据必须分别解释。实际仿真还需复核线圈截面和归属、匝数和极性、材料 B-H 曲线、band 包围和气隙拓扑、运动参数、能量平衡、网格及时间步收敛。

Rotational/translational models were not solved. 3D live behavior, motor benchmarks, external-circuit coupling, nonlinear-material calibration, mesh/time-step independence and engineering acceptance were not validated. API acceptance, native property access, plots and existing data remain distinct evidence levels.

首次在受限进程环境中执行时 PyAEDT 无法正确发现用户桌面会话；该验证进程已停止，后续在能访问该进程的正常执行环境中完成。验证脚本现在在连接前进行 PyAEDT 会话发现检查，发现不到目标时停止，不尝试隐式启动新 AEDT。

An initial restricted execution identity could not discover the desktop session correctly. That verifier was stopped; verification succeeded under an identity with process access. The script now checks PyAEDT discovery before attachment and refuses to proceed when the explicit existing session is absent.
