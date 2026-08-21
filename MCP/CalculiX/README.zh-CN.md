# CalculiX MCP

把开源有限元求解器 **CalculiX**（`ccx`）通过 MCP 暴露给 MCP 客户端。CalculiX 是
GPLv2 协议、无需 license、以 fire-and-forget 方式运行的 CLI——因此本服务器完全自
包含，没有常驻会话 bridge，也没有 license 状态机。

工作流：解析 CalculiX/Abaqus 的 `.inp` 文件 → 检查可调设计变量 → 原位改值 → 提交
给 `ccx` 求解 → 解析文本结果（`.dat`）→ 把 `.dat` 结果导出为 `result_mesh.json`，
供仓库的 [Text to CAE Viewer](../../viewer) 渲染网格与应力场。

这是 hub 中第一个开源求解器的 FEM MCP（既有 FEA 线只到 FEniCS 参考），填补了
Issue #14 提出的空白。

## 工具

| 工具 | 作用 |
| --- | --- |
| `fea_health` | 报告 meshio 可用性与探测到的 `ccx` 可执行文件。 |
| `parse_inp` | 解析 `.inp`：节点、单元计数、壳/梁截面、材料、载荷。 |
| `list_design_vars_tool` | 列出可调设计变量（壳厚、梁截面、材料 E/ν/密度、载荷幅值），每个带 `var_id` 定位器。 |
| `modify_card_tool` | 按 `var_id` 原位修改一个设计变量；纯文本替换，写出新 `.inp`。 |
| `run_solver_tool` | 对 deck 跑 `ccx -i <jobname>`。成功判定不看 exit code（见下）。 |
| `read_results_tool` | 解析 `.dat` 取最大 von Mises（自算）、最大位移、体积、质量；`*FREQUENCY` 步还返回特征值表（`frequencies`、`n_modes`）。 |
| `export_results_tool` | 把本次求解导出为 `result_mesh.json`（viewer 格式）；模态运行传 `mode=N` 可导第 N 阶振型。 |
| `optimize_structure_tool` | 两阶段尺寸优化（LHS 粗扫 + 坐标下降精修）：在应力/位移约束下，通过调标量设计变量（壳厚、梁截面、材料、载荷）最小化质量。仅限壳/梁模型——见[优化](#优化)。 |

## CalculiX 实战契约（编码在 solver 里）

这些才是本服务器的含金量所在——全部来自公开的 CalculiX 行为：

- **ccx exit code 不可信** —— 即使打印 `*ERROR`，`ccx` 也返回 0。成功 = stdout
  无 `*ERROR` **且** `.sta` 有数据行 **且** 未超时。
- **`.dat` 没有 von Mises** —— 只有 6 个应力分量；σ_vm 需自算。
- **`.dat` 没有总体积/质量** —— 由网格几何 × `*DENSITY` 计算。
- **严禁 `meshio.write`** —— 会丢掉全部卡片并把 `B31` 改写成 `B31H`（文件损坏）。
  `modify_card` 走纯文本原位替换。
- **`*FREQUENCY` 步的 `.sta` 只有表头** —— 特征值求解没有增量，因此成功判据也接受
  非空 `.dat`（否则每次模态运行都会被误判失败）。频率和各阶特征向量都在 `.dat`
  文本里，不只在 `.frd`。

## 优化

`optimize_structure_tool` 跑两阶段**尺寸**优化：先 Latin Hypercube 粗扫，再坐标下降
精修，通过原位改标量卡片，在应力/位移约束下最小化质量。

```python
optimize_structure_tool(
    path="examples/bracket.inp",
    variables={"shell.PLATE.thickness": [2.0, 8.0]},
    n_lhs=8, max_solves=18,
)
# -> 最优 ~4.1 mm，减重 ~-48%，应力 < 250 MPa，位移 < 1.5 mm
```

范围与诚实性：

- **仅限壳/梁模型。** 实体（C3D8）没有标量几何卡片可调，没有厚度可减薄；请用
  shape/topology 优化。
- 这是**尺寸/参数优化，不是拓扑优化**——它减薄截面，不在空间上重分布材料。
- 最优 deck 写到输入旁的 `<stem>.optimized.inp`；可交给 `export_results_tool` 渲染。

## 模态分析

`*FREQUENCY` deck 用同一套工具即可。`.dat` 里什么都有：先是
`E I G E N V A L U E   O U T P U T` 特征值表（模态号、特征值、rad/s、cycles/s），
随后是标记为 `E I G E N V A L U E    N U M B E R     N` 的各阶特征向量块——
向量行复用静力 `displacements (vx,vy,vz)` 格式，因此振型导出不碰 `.frd`。

```python
read_results_tool(result_path=...)     # -> frequencies: [{mode, eigenvalue,
                                       #     freq_rad_s, freq_hz}], n_modes
export_results_tool(path="examples/cantilever_modal.inp", mode=1)
# -> result_mesh.json 持有第 1 阶特征向量（无应力振型）
```

两条值得诚实汇报的物理注记：双对称截面出现简并对（f1 = f2）；全积分 C3D8
六面体弯曲剪切锁死，频率比欧拉梁手算偏高 ~5-10%
（`examples/cantilever_modal.inp`：ccx f1 ~ 502 Hz vs 手算 ~ 464 Hz）。

## 安装

在本目录下（Linux/macOS；Windows 请自行调整 venv 激活方式）：

```bash
uv venv .venv --python 3.11
uv pip install --python .venv/bin/python "mcp>=1.0,<1.8" meshio numpy "python-dotenv>=1,<2"
uv pip install --python .venv/bin/python pytest   # 仅开发用
```

> `mcp` 钉在 1.8 以下：`mcp` 2.0 移除了 `mcp.server.fastmcp`（本服务器和 hub 其它
> MCP 都用这个 FastMCP import）。

CalculiX 需单独安装（例如把 `ccx` 或 `ccx_preCICE` 放到 PATH，或设置 `CCX_EXE`）。
`fea_health` 会告诉你是否探测到可执行文件。

## 运行

```bash
.venv/bin/python mcp_server.py          # stdio MCP 传输
```

用 `examples/mcp_config.example.json` 把它注册到 MCP 客户端。

## 示例：悬臂梁 benchmark

`examples/cantilever.inp` 是一个**公开教科书悬臂梁**（钢壳梁，一端固支，另一端横向
受载）。重新生成：

```bash
python3 examples/gen_cantilever.py
```

手算 sanity 目标（欧拉梁，mm-t-s-MPa，P = 100 N）：端部挠度 ≈ 0.8 mm，根部应力
≈ 140 MPa。viewer 会自动放大这个微小的弹性变形以供显示。

`examples/cantilever_modal.inp` 是同一根梁加 5 阶 `*FREQUENCY` 步：f1 = f2 ≈ 502 Hz
（简并对）、f3 = f4 ≈ 3089 Hz、f5 ≈ 6309 Hz，对比手算 f1 ≈ 464 Hz（C3D8 剪切锁死）。
viewer 案例 `models/text-to-cae-calculix-modal` 渲染第 1 阶振型。

## 测试

```bash
.venv/bin/python -m pytest
```

解析层与导出层的测试无需求解器即可运行。求解器测试在未探测到 `ccx` 时自动跳过，
因此在安装 CalculiX 之前测试套件依然全绿。

## 目录

- `mcp_server.py` —— FastMCP stdio 服务器。
- `tools/inp_parser.py` —— `.inp` 卡片解析 + 文本原位改值。
- `tools/solver.py` —— `ccx` 子进程 + `.dat` 结果解析。
- `tools/result_exporter.py` —— `.dat`/`.inp` → `result_mesh.json`（viewer 格式）。
- `tools/optimizer.py` —— 两阶段尺寸优化（LHS + 坐标下降）。
- `examples/` —— 公开悬臂梁 benchmark + 生成器 + MCP 配置示例。
- `tests/` —— pytest 套件。

## 仓库规则

只提交可复用源码、示例（公开 benchmark）、测试与文档。不要提交虚拟环境、`.env`，
以及任何生成的求解器输出（`.frd`、`.dat`、`.sta`、`.cvg`、job 目录）。输入 `.inp`
属于源码，应当提交。
