# 0.5.0 通用工程操作 / Generic engineering operations

## 中文

仍为 **18 个 MCP 工具**，`execute_live_ansa_operation` 的具名操作从 8 项扩展到 **24 项**。
本页新增 16 项，不含任何算例专用入口。参数以连接后
`get_live_capabilities.general_operations.operations` 返回的当前运行时契约为准，必须完整提供。

| 能力 | 新操作 | 范围和限制 |
| --- | --- | --- |
| 拓扑整理 | `topology_paste` | 明确 CONS ID；使用当前容差；明确是否跨 PID；邻接拓扑可能改变 |
| 几何检查/修复 | `repair_geometry` | FACE；cracks、needle_faces、collapsed_cons；repair=false 仅检查；原生修复一轮后复查 |
| 网格尺寸 | `set_perimeter_length` | CONS / FE PERIMETER；正长度，模型单位；不使用全模型默认范围 |
| 通用面网格 | `mesh_faces` | 明确 FACE；使用当前算法、类型和阶次；临时切换 mesh 模式，结束后回读恢复 |
| 四边面映射 | `generate_surface_mesh` | 仅四边 FACE；quad/mixed/ortho_tria；返回实际 meshed_ents，未覆盖面不冒充成功 |
| 体网格 | `generate_volume_mesh` | 已定义的 VOLUME；TETRA FEM / RAPID / CFD；不包含自动封闭坏几何、边界层和六面体分块 |
| 局部重划 | `remesh_shells` | SHELL；CFD/ADVFRNT/FREE/SPOT/GRADUAL；沿用当前网格设置 |
| 质量标准 | `set_mesh_quality_criterion` | SHELL/SOLID；aspect ratio/min length/max length/skewness/warpage/jacobian；CAS 后设置并回读；属于全局设置 |
| 质量检查/修复 | `repair_mesh_quality` | SHELL/SOLID；显式选择 native_fix、smooth_shells 或 reconstruct_shells；后两种仅 SHELL；一轮后复查，不自动循环或换算法 |
| 各向同性材料 | `create_isotropic_material` | Nastran MAT1 / Abaqus MATERIAL；明确 E、nu、rho 和单位约定；逐字段回读 |
| 材料/属性等引用 | `set_entity_references` | 现有实体的原生引用字段；解析目标、旧引用 CAS、新引用 ID+类型回读；不是裸填未经验证的 ID |
| 节点集中力/力矩 | `create_nodal_load` | 当前首发为 Abaqus CLOAD；现有 NODE、STEP，DOF 1–6；每节点值，不做自动合力分配 |
| 节点约束 | `create_nodal_constraint` | Abaqus 初始 BOUNDARY；DOF 组合 1–6；同一给定位移值；不代替所有分析步边界编辑 |
| 接触对 | `create_contact_pair` | Abaqus 非绑定 surface-to-surface；两组非空、不重叠的壳单元 SET、已存在的交互属性和 SPOS/SNEG；不自动识别法向/穿透/接触物理 |
| 求解输入 | `import_solver_deck` | Abaqus / Nastran 与当前 Deck 一致；ASCII 平铺文件 <=32 MiB；SHA256 校验；合并、偏移编号，不替换当前数据库 |
| 求解输出 | `export_solver_deck` | Abaqus Standard / Nastran；全模型单文件、只写新路径；临时目录验证、独占发布、字节数和 SHA256 回读 |

### 小步工作流

1. 查会话、Deck、模型和 API；先保存 `.ansa` 快照。所有写入携带当前
   `expected_database`、`expected_session_nonce`、`expected_deck`、唯一 `operation_id`、`confirm=true`。
2. 用 `list_live_entities` 和 `get_live_entity_fields` 定位实体和 Card 字段。
   单步最多 200 个显式实体 ID；不得把空列表解释为全部模型。
3. 几何先 `repair_geometry(repair=false)`；确认报告、容差及允许邻接改变后，再进行拓扑整理或一轮修复。
4. 明确网格尺寸与当前网格设置，再生成面/体网格。质量标准须由项目要求决定。
   可先用 `execute_live_ansa_python_step` 小步回读，例如：
   `result = base.F11ShellsOptionsGet('aspect ratio')`，然后把原值传给 `set_mesh_quality_criterion.expected_values`。
5. 质量先检查，再选择一种修复方法，查看 before/after 报告。仍有错误必须继续人工判断；
   被重构/删除的原 ID 无法复查时返回 scope_changed/recheck_required，而不是质量通过。
6. 创建材料并用引用操作赋给现有属性；创建载荷/约束/接触后复核单位、工况、作用范围和接触方向。
7. 导出后独立求解、检查日志、收敛和平衡，并做网格收敛与工程复核。

所有操作在现有 GUI 主线程执行，结束请求重绘并记录具体操作名；长原生调用内部不能逐帧显示。
`OUTCOME_UNKNOWN` 表示可能已有部分更改，不自动回滚，也不能换 operation_id 重试。
文件路径必须在 allowed_roots 内。通用导入拒绝 INCLUDE、FILE/INPUT、外部库、用户子程序等
引用及高级控制语句；请先显式扁平化。此检查是保守输入范围限制，不是完整求解器语法解析器或沙箱。
导入器可能忽略其不支持的关键字；导出哈希/成功回读不证明关键字语义无损，不证明作业可求解。
任意 Python 入口仍拥有 ANSA 本机权限，并不受这些文件白名单约束。

### 验证边界

真实原生测试仅覆盖 Windows ANSA **25.1.2**。独立配置和空模型测试，不改用户当前模型。
覆盖材料/引用/载荷/约束/壳接触、Abaqus 导入导出、Nastran 导出再导入、平面四边网格、
通用面网格和盒体四面体网格。畸变测试：aspect ratio 阈值 3，两个壳单元报错；
原生 native_fix 后错误仍在，显式 smooth_shells 后该检查变为 ok。
这仅验证该小模型、该项标准；不是所有网格、全部质量准则或工程精度保证。
几何检查/Topo 已调用验证，但针状面、塌陷边自动修复、重构策略、其他网格算法和其他版本尚未完整实测。
不提供自动求解、META 后处理、塑性材料、实体面接触、全部求解器边界条件的一揽子承诺。

### 安装与升级

安装 0.5.0 `.bpkg` 后保存模型并重启 ANSA，从 Plugins > ANSA MCP > Start 启动。
同时重启 MCP 服务；面板应显示 Runtime 0.5.0，能力查询应返回 24 个具名操作。
现有认证配置沿用，不分发 token。第三方使用无个人路径的 release 包；本机 upgrade 包不用于分发。
详见 [通用配置指南](GENERAL_OPERATIONS.md) 和 [插件安装](README.zh-CN.md)。

## English

Version 0.5.0 retains **18 MCP tools** and expands the named operation catalog from 8 to **24**.
The sixteen new operations in the table cover scoped topology/geometry repair, surface and tetrahedral
volume meshing, remeshing, quality criteria and explicit repair strategies, isotropic materials,
entity-reference assignment, Abaqus nodal loads/initial constraints/shell contact pairs, and flat
Abaqus/Nastran import/export. Query the connected runtime catalog for exact required parameter keys.

Writes require confirmation, current session/database/deck expectations and a unique operation ID.
Scopes contain 1–200 existing IDs; empty never means all. Save a database snapshot first.
Checks and fixes return before/after reports. Native repair, shell smoothing and reconstruction
are separate user-selected strategies, one pass only. A changed entity scope requires re-selection
and a new check. Completion, redraw and file hashes are not mesh quality or engineering certification.
Reference assignments resolve entities and compare old references before writing, then read back ID/type.
Material units are declared, not converted. Load/constraint/contact convenience recipes currently
target Abaqus; Nastran material and solver file I/O are supported. Existing interaction properties,
nonoverlapping shell sets and side orientation are required for contact; physical correctness is not inferred.

Input accepts only basic flat ASCII decks up to 32 MiB, verifies the expected SHA256, imports verified
staged bytes with merge/offset semantics and rejects external references/includes/advanced directives.
This is a conservative format boundary, not a complete parser or sandbox. Native import may omit
unsupported keywords. Export is all-model monolithic Abaqus Standard or Nastran into a NEW allowed-root
path; staged output is checked and published exclusively without overwrite. No semantic-lossless or
solver-readiness guarantee is made. Arbitrary Python remains unrestricted local code execution.

Real tests use an isolated Windows ANSA 25.1.2 process. They exercise materials, reference assignment,
loads, constraints, shell contact, both solver file formats, planar shell meshing and tetrahedra in a box.
A distorted patch had two aspect-ratio failures: native fix retained them; explicit shell smoothing
made that check pass. Other algorithms, hard geometry repairs, reconstruction, versions and production
models remain unverified. No solver execution or META post-processing is added here.

Upgrade using the official BETA Packager Installer, save work and restart ANSA, then Plugins > ANSA MCP >
Start. Restart the external MCP service too. Verify Runtime 0.5.0 and 24 named operations by an authenticated
capability query. Use the portable release package for third parties; machine-specific upgrade packages
are not redistributable. Keep the existing shared configuration path and never distribute credentials.
