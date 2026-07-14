# 复合材料固化仿真 Skill

一个全面的Abaqus仿真技能，用于复合材料固化过程，包含模具接触、摩擦、温度相关材料状态和Model Change回弹分析。

## 概述

本skill提供完整的复合材料固化仿真工作流，包括：

- **模具接触**：温度相关摩擦系数（0.45 → 0.2 → 0.169）
- **四步固化过程**：粘流态 → 橡胶态 → 玻璃态 → 回弹
- **Model Change脱模**：真实回弹物理机制
- **UMAT子程序**（Threestep.for）：三态复合材料本构
- **批量数据集生成**：基于模板INP文件
- **自动ODB提取**：导出CSV并计算回弹角

## 关键：P8_mold vs P8_only

| 特征 | P8_mold（正确） | P8_only（错误） |
|------|-----------------|-----------------|
| 模具部件 | 有（TOOL-1） | 无 |
| 接触 | S1↔S4+S6, HARD, 有摩擦 | 无 |
| 固化约束 | 模具接触（摩擦） | ENCASTRE（全固支） |
| 脱模 | sp步Model Change | 无 |
| 回弹云图 | **不对称**（正确） | **中心对称**（错误） |
| 回弹角 | 正值（0.5°-1.6°） | 不反映真实物理 |

**始终使用 `P8_mold_V2.inp` 作为模板。** 详见 `SKILL.md`。

## Skill架构

```
composite-curing-simulation/
├── SKILL.md                           # 主路由
├── README.md                          # 英文说明
├── README.zh-CN.md                    # 本文件
├── core/
│   └── composite-curing/              # 主路由逻辑
├── modeling/
│   ├── composite-layup/               # 铺层角度、厚度、层数
│   ├── mold-geometry/                 # 模具/TOOL部件设置
│   └── composite-mesh/                # C3D8网格、厚度方向
├── setup/
│   ├── curing-material/               # UMAT、COM/TOOL材料
│   ├── curing-contact/                # 接触对、摩擦 ★
│   ├── curing-bc/                     # 边界条件 ★
│   ├── curing-load/                   # 内表面压力
│   └── curing-temperature/            # 温度场
├── analysis/
│   ├── curing-steps/                  # 四步过程（vis/rub/glassy/sp）
│   └── springback-analysis/           # Model Change、脱模
├── execution/
│   ├── curing-job/                    # UMAT作业提交
│   └── socket-bridge/                 # Socket桥接连接
├── postprocessing/
│   ├── odb-extraction/                # ODB场输出读取
│   └── csv-export/                    # CSV导出（坐标+位移）
└── reference/
    └── curing-parameters/             # 完整参数表
```

★ = 已加固模具约束细节

## 关联Skill

**[abaqus-odb-extraction](../abaqus-odb-extraction/SKILL.md)** — 独立skill，用于批量ODB提取、SVD双臂平面拟合回弹角计算、标准化云图截图（隐藏模具）。包含完整API参考、文件系统隔离指南和错误排查表。

## 约束条件详解

### 固化阶段（vis/rub/glassy）

| 约束对象 | 约束方式 | 目的 |
|---------|---------|------|
| TOOL-1 | U1=0, U2=0（_PickedSet327/328） | 固定模具空间位置 |
| 复合材料 | 模具摩擦接触 | 允许滑动和热膨胀 |

### 回弹阶段（sp）

| 约束对象 | 约束方式 | 目的 |
|---------|---------|------|
| TOOL-1 | Model Change移除 | 模具消失 |
| 接触对 | Model Change移除 | 无接触 |
| 复合材料Set-2 | `*Boundary, op=NEW` U1=U2=U3=0 | 仅防止刚体位移 |

### 为什么P8_only是错误的

1. **无模具接触**：没有TOOL部件，固化期间无摩擦约束，复合材料被ENCASTRE人为固定
2. **无脱模过程**：缺少`*Model Change`步骤，无真实回弹机制
3. **中心对称假象**：ENCASTRE创建对称约束模式，导致对称变形
4. **缺失摩擦历史**：温度相关摩擦（0.45→0.2→0.169）捕获材料状态转换，无接触时完全缺失

## 关键参数

| 参数 | 值 |
|------|-----|
| 模板INP | P8_mold_V2.inp |
| UMAT | Threestep.for（4434字节） |
| 铺层数 | 8 |
| 单层厚度 | 0.250 mm |
| 角度选项 | {-45, 0, 45, 90} |
| 每案例节点数 | 5445（P8-1实例） |
| ODB大小 | ~122.4 MB/案例 |
| 摩擦系数 | vis=0.45, rub=0.2, glassy=0.169 |
| 压力 | 0.6 MPa（S2内表面） |
| 回弹步 | sp（Model Change + Set-2 BC） |

## 数据集统计（100案例）

| 统计量 | 值 |
|--------|-----|
| 总案例数 | 100 |
| 成功率 | 100% |
| 回弹角均值 | 1.22° |
| 回弹角标准差 | 0.20° |
| 回弹角范围 | 0.51° - 1.64° |
| 全部为正 | 是（物理正确） |

## 快速开始

1. **单个案例**：通过 `core/composite-curing` 路由到相应子skill
2. **批量数据集**：按照 `SKILL.md` 中"Dataset Generation"部分操作
3. **ODB提取**：使用独立的 `abaqus-odb-extraction` skill
4. **云图截图**：使用 `abq2020.bat cae noGUI` 配合 `LeafFromPartInstance` 隐藏模具

## 文件

- `P8_mold_V2.inp` — 正确模板（含模具）
- `P8_only_recipe_1.inp` — 错误模板（已归档，请勿使用）
- `Threestep.for` — UMAT子程序
- `abaqusis.env` — 环境配置

## 版本

更新日期：2026-07-14
