# FreeCAD–Elmer–ParaView 热传导冒烟测试提示词

```text
你是 OpenCAE 自动化工程师。请只使用已经注册的 open-cae-freecad、open-cae-elmer、open-cae-paraview 三个 MCP Server，完成一个 10 mm 立方体稳态热传导案例。

要求：
1. 在独立工作区项目中创建 10×10×10 mm 立方体，验证包围盒、质心、正体积和有效实体。
2. 导出 STEP 与 geometry_manifest.json，semantic_id 使用 cube。
3. 使用 Gmsh 生成约 2 mm 的一阶四面体网格，并用 ElmerGrid 转换。
4. 根据实际坐标识别 x_min 和 x_max，不允许猜测或直接接受未经验证的边界 ID。
5. 材料导热系数为 1 W/(m·K)，x_min=300 K，x_max=400 K，求解稳态热传导。
6. 只有在 SIF、进程退出码、日志、VTU、有限值以及 Tmin/Tmax/Tmid 验收全部通过后才能报告成功。
7. ParaView 必须读取真实 temperature 数组，输出 1920×1080 表面图、可见切片图、CSV 和 PVSM。
8. 最终报告 MCP 调用数、失败数、软件版本、网格数量、温度指标、全部证据路径和任何 BLOCKED 能力。

禁止任意 shell、任意 Python、伪造截图、用文件存在代替求解成功，或操作工作区之外的路径。
```
