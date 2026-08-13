# FEP Agent Hub

FEP Agent Hub 是面向 Codex 的 FreeCAD、Elmer FEM、ParaView 三软件独立 MCP 自动化仓库。

本目录是 CAE-Agent-Hub 的集成副本；包含精选媒体资产的完整独立项目维护在 [S2mon123/FEP-Agent-Hub](https://github.com/S2mon123/FEP-Agent-Hub)。

名称中的 FEP 分别代表：

- **F — FreeCAD**：参数化 CAD、几何验证、FCStd 和 STEP 交接。
- **E — Elmer FEM**：Gmsh 网格、ElmerGrid 转换、结构化 SIF、求解和物理结果验收。
- **P — ParaView**：持久化无界面后处理、字段检查、过滤器、PNG、CSV 和 PVSM。

## 当前验证状态

- 三个 MCP 共暴露 49 个工具，49/49 均完成实际契约覆盖。
- 完整验证共调用 52 次，52/52 契约通过。
- 46 个可执行工具能力返回 `SUCCEEDED`。
- 完整矩阵中 3 个上下文不成立的调用按设计返回 `BLOCKED`：FreeCAD 无界面截图、热 profile 下的电磁激励、单时间步稳态数据动画；具有多个已验证时间步的数据可以导出动画帧。
- 10 mm 立方体稳态热传导案例通过：Tmin≈300 K、Tmax≈400 K、Tmid≈350.27 K。
- 真实瞬态热案例通过 20/20 个 BDF1 时间步，20 s 跨中温度与 Fourier 解析值相差 0.318 K。
- 二维谐波开路变压器效应案例通过字段、磁通、电压、线性、网格敏感性和 ParaView 验收。
- 二维平面应力简支梁通过 10/10 准静态载荷级、理论挠度/应力/应变门槛和 10 帧 ParaView 导出。
- 二维稳态层流通道在 Re=100 下通过 Poiseuille 速度剖面、流量、无滑移与压力降门槛。
- 二维楞次定律瞬态涡流案例通过 40/80/40 个原生时间步、四段反向符号门禁、时间/网格敏感性和 40 帧 ParaView 导出。
- 常规自动测试实际执行 17 项，17/17 通过；启动本机 CAE 软件的 pytest 包装测试为显式 opt-in。

这里所说的 100% 是“已声明工具契约覆盖与本案例验收 100%”，不等于所有未来几何和物理问题都已经验证。

## 分类结构

```text
FEP_Agent_Hub/
├── mcp/
│   ├── freecad/                 # 15 个工具
│   ├── elmer/                   # 17 个工具
│   └── paraview/                # 17 个工具
├── packages/open-cae-core/      # 公共安全、工作区和证据模块
├── configs/                     # 公开模板与本机配置
├── docs/                        # 架构、接口和验证报告
├── examples/                    # 热、电磁、结构与流体轻量证据
├── prompts/                     # 可复用工作流提示词
├── checklists/                  # 验收清单
├── scripts/                     # 安装、诊断、注册、冒烟测试
├── tests/
└── workspace/                   # 本机生成，Git 忽略
```

## Codex Skill

CAE Agent Hub 内置 [`Skill/fep-agent-hub`](../../Skill/fep-agent-hub/SKILL.md) 可复用 Skill，负责路由 6 个已验证 profile、固定 FreeCAD → Elmer FEM → ParaView 调用次序，并区分流程通过率与数值误差口径。

示例调用：`使用 $fep-agent-hub 执行并验收一个瞬态热传导基准。`

## 安装

先复制配置模板并填写本机软件位置：

```powershell
Copy-Item .\configs\open-cae.example.toml .\configs\open-cae.local.toml
.\scripts\install.ps1
```

Windows 上部分原生 CAE 程序对非 ASCII 命令行路径兼容性有限，建议把 `[workspace].root` 配置为纯英文短路径；代码仓库本身可以位于中文目录。

执行基础测试：

```powershell
$env:OPEN_CAE_CONFIG = "$PWD\configs\open-cae.local.toml"
.\.venv\Scripts\python.exe .\scripts\doctor.py
.\.venv\Scripts\python.exe .\scripts\protocol_smoke.py
.\.venv\Scripts\python.exe -m pytest -q
```

执行真实软件链：

```powershell
.\scripts\run-smoke.ps1
```

注册到 Codex：

```powershell
.\scripts\register-codex.ps1
codex mcp list
```

通过 MCP 协议执行案例和全部工具验证：

```powershell
.\.venv\Scripts\python.exe .\scripts\mcp_heat_smoke.py
.\.venv\Scripts\python.exe .\scripts\mcp_transformer_smoke.py
.\.venv\Scripts\python.exe .\scripts\mcp_beam_smoke.py
.\.venv\Scripts\python.exe .\scripts\mcp_transient_heat_smoke.py
.\.venv\Scripts\python.exe .\scripts\mcp_channel_flow_smoke.py
.\.venv\Scripts\python.exe .\scripts\mcp_lenz_eddy_smoke.py --variants full
.\.venv\Scripts\python.exe .\scripts\mcp_full_validation.py
```

## 关键文档

- [发布验证报告](docs/release-validation-report.md)
- [二维谐波变压器验证报告](docs/transformer-induction-validation-report.zh-CN.md)
- [二维简支梁验证报告](docs/simply-supported-beam-validation-report.zh-CN.md)
- [楞次定律瞬态涡流耦合电磁场验证报告](docs/lenz-law-transient-eddy-current-validation-report.zh-CN.md)
- [五案例 60 秒综合研究视频验证](docs/five-case-research-video-validation.zh-CN.md)
- [瞬态热传导与二维层流验证报告](docs/transient-heat-and-flow-validation-report.zh-CN.md)
- [四案例 30 秒研究展示视频与误差复核](docs/four-case-research-video-validation.zh-CN.md)
- [三软件案例总结](docs/OpenCAE_MCP_三软件协同仿真冒烟测试总结报告.md)
- [架构](docs/architecture.md)
- [安全设计](docs/security.md)
- [数据清单](docs/manifests.md)
- [测试说明](docs/testing.md)

## 安全原则

- 只允许工作区内路径。
- 原生程序使用白名单和参数数组启动，不开放任意命令执行。
- FreeCAD 仅运行固定 Runner，不接收任意 Python。
- ParaView worker 由 MCP 独占管理，不关闭用户手动启动的 GUI。
- 不能验证的能力返回 `BLOCKED`，不能伪造成功文件。

## 许可

仓库代码采用 MIT License。FreeCAD、Gmsh、Elmer 和 ParaView 需由使用者自行安装，本仓库不重新分发这些软件。
