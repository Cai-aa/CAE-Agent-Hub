# 有限元仿真 Skills

这个目录下的可复用 CAE 仿真 skills 按求解器或领域分组。

当前结构：

| 文件夹 | 内容 |
| --- | --- |
| `abaqus/core` | Abaqus 主工作流 skill。 |
| `abaqus/modeling` | 几何、材料、相互作用、网格相关 skills。 |
| `abaqus/setup` | 载荷、边界条件、分析步、幅值、场、输出和文档相关 skills。 |
| `abaqus/analysis` | 静力、动力、模态、热、接触、耦合和疲劳分析 skills。 |
| `abaqus/execution` | 作业提交和导出 skills。 |
| `abaqus/postprocessing` | ODB/结果后处理 skills。 |
| `abaqus/optimization` | 拓扑优化、形状优化和通用优化 skills。 |
| `abaqus/reference` | 可配合 Abaqus 使用的通用 FEA 和 FEniCS 参考 skills。 |
| `CST` | 配合 CST MCP 使用的 CST Studio Suite 电磁仿真流程 skills。 |
| `fep-agent-hub` | FreeCAD、Elmer FEM、ParaView 证据优先协同 Skill，包含 6 个已验证 CAE profile。 |

完整索引、上游来源和客户端使用方法见 [abaqus/README.zh-CN.md](abaqus/README.zh-CN.md)。
CST workflow skills 见 [CST/README.zh-CN.md](CST/README.zh-CN.md)。
FEP 三软件协同流程与基准参考见 [fep-agent-hub/SKILL.md](fep-agent-hub/SKILL.md)。

English version: [README.md](README.md).
