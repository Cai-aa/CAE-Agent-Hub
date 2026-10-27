# 仿真结果完整图集 / Full simulation atlas

[中文主页](../README.zh-CN.md) · [English homepage](../README.md) · [详细校核说明](simulation-showcase.md)

共 **37 项结果展示**，涵盖多工况与同一模型的不同结果视图；不把这些条目数当作独立工程数量。原生图片逐字节复制，新图仅使用已保存的求解数据或归档指标。

This atlas covers result views, not a count of independent engineering projects. Original images are copied unchanged. New plots use saved solver fields, native logs, or archived metrics; no new solve was run for this update.

七份Abaqus ODB已在本轮只读打开，诊断状态均为 `JOB_STATUS_COMPLETED_SUCCESSFULLY`。新绘场图只绘真实单元外表面：高阶单元显示为角点平面，颜色为单元积分点Mises均值；振型单独归一化，变形倍率在图下注明。它们不是Abaqus原生云图，也不能替代原生结果精度审查。

Seven original Abaqus ODBs were opened read-only in this review and reported successful completion. Replotted fields use external corner faces and element-mean integration-point Mises; modes are normalized separately. These are simplified field renderings, not native Abaqus contours or independent engineering validation.

CST为Design Studio电路S参数；Elmer图来自集成仓库自带的已验证基准指标。Radioss曲线保留原生日志误差的符号，正常退出不等于能量或接触已通过全部工程检查。

CST plots describe circuit S-parameters. Elmer plots use the integration repository’s recorded benchmark metrics. Radioss charts preserve the signed native energy error; normal termination alone does not certify energy or contact accuracy.

## 目录 / Contents

- [COMSOL · 散热片稳态传热 / COMSOL · Steady heatsink](#heatsink)
- [Icepak · 65 W CPU风冷 / Icepak · 65 W CPU cooling](#cpu)
- [COMSOL · 二维稳态热传导 / COMSOL · 2D heat conduction](#comsol2d)
- [Elmer · 立方体稳态导热 / Elmer · Steady heat cube](#fep-steady)
- [Elmer · 真实瞬态导热 / Elmer · Transient heat conduction](#fep-transient)
- [Mechanical · 100 N悬臂梁 / Mechanical · 100 N cantilever](#cantilever)
- [ANSA → Abaqus · 原生全六面体支架 / ANSA → Abaqus · Native all-hex bracket](#bracket-hex)
- [ANSA → Abaqus · 二次四面体支架 / ANSA → Abaqus · Quadratic tet bracket](#bracket-tet)
- [OptiStruct / HyperView · 三维梁 / OptiStruct / HyperView · 3D beam](#optistruct-beam)
- [Abaqus · 早期三维悬臂梁 / Abaqus · Solid cantilever](#abaqus-beam)
- [Abaqus · 500 N梁静力与模态 / Abaqus · 500 N static/modal beam](#beam500)
- [Abaqus · 带孔板应力集中 / Abaqus · Plate with a hole](#hole-static)
- [Abaqus · 带孔板第一阶振型 / Abaqus · First plate mode](#hole-modal)
- [Abaqus · 三层框架动力响应 / Abaqus · Three-story frame dynamics](#frame)
- [Abaqus · 框架六阶模态 / Abaqus · Six frame modes](#frame-modal)
- [Abaqus/Explicit · 球撞板 / Abaqus/Explicit · Sphere impact](#sphere-impact)
- [Abaqus/Explicit · 正交切削算例 / Abaqus/Explicit · Orthogonal cutting](#cutting)
- [Abaqus/Explicit · 三维铣削载荷响应 / Abaqus/Explicit · Milling load response](#milling)
- [Abaqus/Explicit · 弹丸冲击板件 / Abaqus/Explicit · Projectile/plate impact](#bullet-impact)
- [Fluent · 90°弯管层流 / Fluent · Laminar 90° elbow](#elbow)
- [Elmer · 平面通道层流 / Elmer · Planar laminar channel](#fep-channel)
- [Maxwell 3D · 旋转电磁执行器 / Maxwell 3D · Rotational actuator](#maxwell)
- [CST Design Studio · 电路S参数 / CST Design Studio · Circuit S-parameters](#cst)
- [Elmer · 二维谐波变压器 / Elmer · 2D harmonic transformer](#fep-transformer)
- [Elmer · 楞次定律瞬态涡流 / Elmer · Transient eddy currents](#fep-lenz)
- [Elmer · 简支梁应力应变 / Elmer · Simply supported beam](#fep-beam)
- [Radioss · 实体轴向碰撞 / Radioss · Axial solid collision](#radioss-axial)
- [Radioss · 落锤算例 / Radioss · Drop-weight benchmark](#radioss-drop)
- [Radioss · 板件冲击 / Radioss · Plate impact](#radioss-plate)
- [Radioss · 块体碰撞 / Radioss · Block impact](#radioss-block)
- [OptiStruct · 固有频率谱 / OptiStruct · Frequency spectrum](#optistruct-modal)
- [OptiStruct · 线性屈曲特征值 / OptiStruct · Linear buckling eigenvalues](#optistruct-buckling)
- [HyperView · 1000 N L形支架归档 / HyperView · Archived 1000 N L-bracket](#hyperview-bracket)
- [CalculiX · 悬臂梁静力归档 / CalculiX · Archived static beam](#calculix-static)
- [CalculiX · 第一阶振型归档 / CalculiX · Archived first mode](#calculix-modal)
- [Mechanical · 齿轮接触校准工况 / Mechanical · Gear contact calibration](#gear-calibration)
- [Icepak · 热块接口验收算例 / Icepak · Heat-block interface acceptance](#icepak-smoke)

## 热管理与传热 / Thermal management

<a id="heatsink"></a>

### COMSOL · 散热片稳态传热 / COMSOL · Steady heatsink

20/30 W与两级网格；30 W细网格 Tmax=80.403 °C。

Two powers and two meshes; 30 W fine-mesh Tmax=80.403 °C.

证据标签 / Evidence label: `saved-solve`。源归档记录 / Source record: `COMSOL_Heatsink_Analysis/rerun_20261025_1545/06_validation/validation_summary.json`。

![COMSOL · 散热片稳态传热](../assets/readme/heatsink-result.png)

<details>
<summary>展开其余 24 张结果与校核图 / More result and check images</summary>

**fine_20W_base_temperature.png**

![fine_20W_base_temperature.png](../assets/readme/heatsink--fine_20W_base_temperature.png)

**fine_20W_convection_flux.png**

![fine_20W_convection_flux.png](../assets/readme/heatsink--fine_20W_convection_flux.png)

**fine_20W_fin_temperature.png**

![fine_20W_fin_temperature.png](../assets/readme/heatsink--fine_20W_fin_temperature.png)

**fine_20W_heat_flux.png**

![fine_20W_heat_flux.png](../assets/readme/heatsink--fine_20W_heat_flux.png)

**fine_20W_heat_flux_vectors.png**

![fine_20W_heat_flux_vectors.png](../assets/readme/heatsink--fine_20W_heat_flux_vectors.png)

**fine_20W_temperature.png**

![fine_20W_temperature.png](../assets/readme/heatsink--fine_20W_temperature.png)

**fine_30W_base_temperature.png**

![fine_30W_base_temperature.png](../assets/readme/heatsink--fine_30W_base_temperature.png)

**fine_30W_convection_flux.png**

![fine_30W_convection_flux.png](../assets/readme/heatsink--fine_30W_convection_flux.png)

**fine_30W_fin_temperature.png**

![fine_30W_fin_temperature.png](../assets/readme/heatsink--fine_30W_fin_temperature.png)

**fine_30W_heat_flux.png**

![fine_30W_heat_flux.png](../assets/readme/heatsink--fine_30W_heat_flux.png)

**fine_30W_heat_flux_vectors.png**

![fine_30W_heat_flux_vectors.png](../assets/readme/heatsink--fine_30W_heat_flux_vectors.png)

**fine_30W_temperature.png**

![fine_30W_temperature.png](../assets/readme/heatsink--fine_30W_temperature.png)

**fine_mesh.png**

![fine_mesh.png](../assets/readme/heatsink--fine_mesh.png)

**coarse_20W_base_temperature.png**

![coarse_20W_base_temperature.png](../assets/readme/heatsink--coarse_20W_base_temperature.png)

**coarse_20W_fin_temperature.png**

![coarse_20W_fin_temperature.png](../assets/readme/heatsink--coarse_20W_fin_temperature.png)

**coarse_20W_temperature.png**

![coarse_20W_temperature.png](../assets/readme/heatsink--coarse_20W_temperature.png)

**coarse_30W_base_temperature.png**

![coarse_30W_base_temperature.png](../assets/readme/heatsink--coarse_30W_base_temperature.png)

**coarse_30W_fin_temperature.png**

![coarse_30W_fin_temperature.png](../assets/readme/heatsink--coarse_30W_fin_temperature.png)

**coarse_30W_temperature.png**

![coarse_30W_temperature.png](../assets/readme/heatsink--coarse_30W_temperature.png)

**coarse_mesh.png**

![coarse_mesh.png](../assets/readme/heatsink--coarse_mesh.png)

**fin_centerline_comparison.png**

![fin_centerline_comparison.png](../assets/readme/heatsink--fin_centerline_comparison.png)

**fin_root_heat_flux_comparison.png**

![fin_root_heat_flux_comparison.png](../assets/readme/heatsink--fin_root_heat_flux_comparison.png)

**power_temperature_comparison.png**

![power_temperature_comparison.png](../assets/readme/heatsink--power_temperature_comparison.png)

**base_bottom_hotspots.png**

![base_bottom_hotspots.png](../assets/readme/heatsink--base_bottom_hotspots.png)

</details>

<a id="cpu"></a>

### Icepak · 65 W CPU风冷 / Icepak · 65 W CPU cooling

30/40/50 CFM三工况；50 CFM CPU最高温度51.7194 °C。固定流量入口等效风扇。

30/40/50 CFM; 50 CFM CPU peak=51.7194 °C. Prescribed-flow fan equivalent.

证据标签 / Evidence label: `saved-solve`。源归档记录 / Source record: `simulations/icepak_cpu_air_cooling/evidence/engineering_report.md`。

![Icepak · 65 W CPU风冷](../assets/readme/cpu--50cfm_temperature_cpu_ihs_tim.jpg)

<details>
<summary>展开其余 6 张结果与校核图 / More result and check images</summary>

**50cfm_pressure_xz.jpg**

![50cfm_pressure_xz.jpg](../assets/readme/cpu--50cfm_pressure_xz.jpg)

**50cfm_speed_fin_channel.jpg**

![50cfm_speed_fin_channel.jpg](../assets/readme/cpu--50cfm_speed_fin_channel.jpg)

**50cfm_speed_xz.jpg**

![50cfm_speed_xz.jpg](../assets/readme/cpu--50cfm_speed_xz.jpg)

**50cfm_temperature_heatsink.jpg**

![50cfm_temperature_heatsink.jpg](../assets/readme/cpu--50cfm_temperature_heatsink.jpg)

**50cfm_temperature_xz.jpg**

![50cfm_temperature_xz.jpg](../assets/readme/cpu--50cfm_temperature_xz.jpg)

**50cfm_velocity_vector_fin_channel.jpg**

![50cfm_velocity_vector_fin_channel.jpg](../assets/readme/cpu--50cfm_velocity_vector_fin_channel.jpg)

</details>

<a id="comsol2d"></a>

### COMSOL · 二维稳态热传导 / COMSOL · 2D heat conduction

300–400 K矩形板；面积平均350 K，解析解误差约3.35×10⁻¹¹ K。

300–400 K rectangle; area mean=350 K; analytical error ≈3.35e-11 K.

证据标签 / Evidence label: `saved-solve`。源归档记录 / Source record: `MCP/COMSOL/comsol_runs/shared_desktop/pde2d_live_20261025/README.md`。

![COMSOL · 二维稳态热传导](../assets/readme/comsol2d--temperature.png)

## 结构静力与模态 / Structures and modes

<a id="cantilever"></a>

### Mechanical · 100 N悬臂梁 / Mechanical · 100 N cantilever

最大总变形0.79651 mm；三档网格与力、力矩、功—能核查。

Max total deformation=0.79651 mm; three meshes and balance checks.

证据标签 / Evidence label: `saved-solve`。源归档记录 / Source record: `workspace/cantilever_visible_20261018_1133/review_20261018/audit_results.json`。

![Mechanical · 100 N悬臂梁](../assets/readme/cantilever-result.png)

<details>
<summary>展开其余 8 张结果与校核图 / More result and check images</summary>

**stress_fine.png**

![stress_fine.png](../assets/readme/cantilever--stress_fine.png)

**z_deformation_fine.png**

![z_deformation_fine.png](../assets/readme/cantilever--z_deformation_fine.png)

**reaction_force.png**

![reaction_force.png](../assets/readme/cantilever--reaction_force.png)

**reaction_moment.png**

![reaction_moment.png](../assets/readme/cantilever--reaction_moment.png)

**mesh_coarse.png**

![mesh_coarse.png](../assets/readme/cantilever--mesh_coarse.png)

**mesh_fine.png**

![mesh_fine.png](../assets/readme/cantilever--mesh_fine.png)

**mesh_medium.png**

![mesh_medium.png](../assets/readme/cantilever--mesh_medium.png)

**mesh_sensitivity.png**

![mesh_sensitivity.png](../assets/readme/cantilever--mesh_sensitivity.png)

</details>

<a id="bracket-hex"></a>

### ANSA → Abaqus · 原生全六面体支架 / ANSA → Abaqus · Native all-hex bracket

1000 N；细网格111万C3D8I；区域应力与整体响应通过预声明敏感性检查，角度警告保留。

1000 N; 1.11M C3D8I elements; scoped response checks pass; angle warnings retained.

证据标签 / Evidence label: `saved-solve`。源归档记录 / Source record: `ansa_runs/bracket_native_hex_20260927/VALIDATION_REPORT.md`。

![ANSA → Abaqus · 原生全六面体支架](../assets/readme/bracket-hex--235_fine_mises_average75.png)

<details>
<summary>展开其余 5 张结果与校核图 / More result and check images</summary>

**232_fine_U3_scale1.png**

![232_fine_U3_scale1.png](../assets/readme/bracket-hex--232_fine_U3_scale1.png)

**233_fine_U3_scale100.png**

![233_fine_U3_scale100.png](../assets/readme/bracket-hex--233_fine_U3_scale100.png)

**234_fine_mises_no_node_average.png**

![234_fine_mises_no_node_average.png](../assets/readme/bracket-hex--234_fine_mises_no_node_average.png)

**204_internal_hex_cut.png**

![204_internal_hex_cut.png](../assets/readme/bracket-hex--204_internal_hex_cut.png)

**288_final_fine_mesh.png**

![288_final_fine_mesh.png](../assets/readme/bracket-hex--288_final_fine_mesh.png)

</details>

<a id="bracket-tet"></a>

### ANSA → Abaqus · 二次四面体支架 / ANSA → Abaqus · Quadratic tet bracket

三档有效C3D10网格；细网格最大位移0.203937 mm。外部CAD几何，ANSA前处理。

Three valid C3D10 meshes; fine max displacement=0.203937 mm; external CAD geometry.

证据标签 / Evidence label: `saved-solve`。源归档记录 / Source record: `ansa_runs/bracket_dual_rib_20260927_0029/验证报告.md`。

![ANSA → Abaqus · 二次四面体支架](../assets/readme/bracket-tet--refined_mises_nodal_average_75_30x.png)

<details>
<summary>展开其余 6 张结果与校核图 / More result and check images</summary>

**refined_mises_unaveraged_element_nodal_30x.png**

![refined_mises_unaveraged_element_nodal_30x.png](../assets/readme/bracket-tet--refined_mises_unaveraged_element_nodal_30x.png)

**refined_U3_30x.png**

![refined_U3_30x.png](../assets/readme/bracket-tet--refined_U3_30x.png)

**refined_U_magnitude_true_scale.png**

![refined_U_magnitude_true_scale.png](../assets/readme/bracket-tet--refined_U_magnitude_true_scale.png)

**fine_mises_nodal_average_75_30x.png**

![fine_mises_nodal_average_75_30x.png](../assets/readme/bracket-tet--fine_mises_nodal_average_75_30x.png)

**fine_mises_unaveraged_element_nodal_30x.png**

![fine_mises_unaveraged_element_nodal_30x.png](../assets/readme/bracket-tet--fine_mises_unaveraged_element_nodal_30x.png)

**coarse_v2_U3_30x_full.png**

![coarse_v2_U3_30x_full.png](../assets/readme/bracket-tet--coarse_v2_U3_30x_full.png)

</details>

<a id="optistruct-beam"></a>

### OptiStruct / HyperView · 三维梁 / OptiStruct / HyperView · 3D beam

原生日志 ANALYSIS COMPLETED；保留位移、应力和支反力云图。

Native ANALYSIS COMPLETED record; displacement, stress, and reaction contours.

证据标签 / Evidence label: `saved-solve`。源归档记录 / Source record: `MCP/HyperWorks/workspace/projects/project_20260917_204357_4b552e/runs/optistruct_20260917_205006_1071a5/input/HW_3D_Cantilever_Beam_P04_Solved.out`。

![OptiStruct / HyperView · 三维梁](../assets/readme/optistruct-beam--P05_Stress_VonMises.png)

<details>
<summary>展开其余 3 张结果与校核图 / More result and check images</summary>

**P05_Displacement_Magnitude.png**

![P05_Displacement_Magnitude.png](../assets/readme/optistruct-beam--P05_Displacement_Magnitude.png)

**P05_Displacement_Z.png**

![P05_Displacement_Z.png](../assets/readme/optistruct-beam--P05_Displacement_Z.png)

**P05_SPCF_Z.png**

![P05_SPCF_Z.png](../assets/readme/optistruct-beam--P05_SPCF_Z.png)

</details>

<a id="abaqus-beam"></a>

### Abaqus · 早期三维悬臂梁 / Abaqus · Solid cantilever

只读原始ODB，完成状态已回读；场图由真实单元结果重新绘制。

Completed status read from the original ODB; newly plotted actual element fields.

证据标签 / Evidence label: `saved-solve`。源归档记录 / Source record: `assets/readme/abaqus-beam-record.json`。

![Abaqus · 早期三维悬臂梁](../assets/readme/abaqus-beam-result.png)

<a id="beam500"></a>

### Abaqus · 500 N梁静力与模态 / Abaqus · 500 N static/modal beam

同一Job先模态后静力；f1≈16.7386 Hz，端部|U2|≈29.6812 mm。

One job, frequency then static; f1≈16.7386 Hz; tip |U2|≈29.6812 mm.

证据标签 / Evidence label: `saved-solve`。源归档记录 / Source record: `abaqus_runs/cantilever_500N_20261025/REPORT.zh-CN.md`。

![Abaqus · 500 N梁静力与模态](../assets/readme/beam500-reference.png)

<a id="hole-static"></a>

### Abaqus · 带孔板应力集中 / Abaqus · Plate with a hole

实际ODB静力场；外表面颜色为单元积分点Mises均值，非原生节点平均图。

Actual static ODB; surface color uses element-mean integration-point Mises.

证据标签 / Evidence label: `saved-solve`。源归档记录 / Source record: `assets/readme/hole-static-record.json`。

![Abaqus · 带孔板应力集中](../assets/readme/hole-static-result.png)

<a id="hole-modal"></a>

### Abaqus · 带孔板第一阶振型 / Abaqus · First plate mode

ODB第一正频率约170.72 Hz；归一化振型，不代表受载位移。

First positive ODB frequency≈170.72 Hz; normalized mode, not loaded displacement.

证据标签 / Evidence label: `saved-solve`。源归档记录 / Source record: `assets/readme/hole-modal-record.json`。

![Abaqus · 带孔板第一阶振型](../assets/readme/hole-modal-result.png)

<a id="frame-modal"></a>

### Abaqus · 框架六阶模态 / Abaqus · Six frame modes

同一框架的六阶模态结果；归一化特征向量，非动力位移幅值。

Six modes of the same frame; normalized eigenvectors, not dynamic amplitudes.

证据标签 / Evidence label: `saved-solve`。源归档记录 / Source record: `Abaqus_ThreeStory_Dynamics/rerun_20261025/06_validation/modal_mesh_convergence.json`。

![Abaqus · 框架六阶模态](../assets/readme/frame-modal--mode_01.png)

<details>
<summary>展开其余 5 张结果与校核图 / More result and check images</summary>

**mode_02.png**

![mode_02.png](../assets/readme/frame-modal--mode_02.png)

**mode_03.png**

![mode_03.png](../assets/readme/frame-modal--mode_03.png)

**mode_04.png**

![mode_04.png](../assets/readme/frame-modal--mode_04.png)

**mode_05.png**

![mode_05.png](../assets/readme/frame-modal--mode_05.png)

**mode_06.png**

![mode_06.png](../assets/readme/frame-modal--mode_06.png)

</details>

## 瞬态动力与加工载荷 / Dynamics and machining loads

<a id="frame"></a>

### Abaqus · 三层框架动力响应 / Abaqus · Three-story frame dynamics

20/30 kN；20 kN层顶最大绝对平均位移1.476 mm。原生云图变形放大300倍。

20/30 kN; 20 kN roof peak mean=1.476 mm. Native contour scale: 300×.

证据标签 / Evidence label: `saved-solve`。源归档记录 / Source record: `Abaqus_ThreeStory_Dynamics/rerun_20261025/06_validation/validation_summary.json`。

![Abaqus · 三层框架动力响应](../assets/readme/frame-result.png)

<details>
<summary>展开其余 24 张结果与校核图 / More result and check images</summary>

**A_20kN_acceleration.png**

![A_20kN_acceleration.png](../assets/readme/frame--A_20kN_acceleration.png)

**A_20kN_balance.png**

![A_20kN_balance.png](../assets/readme/frame--A_20kN_balance.png)

**A_20kN_displacement.png**

![A_20kN_displacement.png](../assets/readme/frame--A_20kN_displacement.png)

**A_20kN_energy.png**

![A_20kN_energy.png](../assets/readme/frame--A_20kN_energy.png)

**A_20kN_interstory.png**

![A_20kN_interstory.png](../assets/readme/frame--A_20kN_interstory.png)

**A_20kN_stress.png**

![A_20kN_stress.png](../assets/readme/frame--A_20kN_stress.png)

**A_20kN_velocity.png**

![A_20kN_velocity.png](../assets/readme/frame--A_20kN_velocity.png)

**A_beam_S11.png**

![A_beam_S11.png](../assets/readme/frame--A_beam_S11.png)

**A_U_end.png**

![A_U_end.png](../assets/readme/frame--A_U_end.png)

**A_U_free_vibration.png**

![A_U_free_vibration.png](../assets/readme/frame--A_U_free_vibration.png)

**A_U_pulse_end.png**

![A_U_pulse_end.png](../assets/readme/frame--A_U_pulse_end.png)

**A_U_pulse_peak.png**

![A_U_pulse_peak.png](../assets/readme/frame--A_U_pulse_peak.png)

**A_U_top_peak.png**

![A_U_top_peak.png](../assets/readme/frame--A_U_top_peak.png)

**B_30kN_acceleration.png**

![B_30kN_acceleration.png](../assets/readme/frame--B_30kN_acceleration.png)

**B_30kN_balance.png**

![B_30kN_balance.png](../assets/readme/frame--B_30kN_balance.png)

**B_30kN_displacement.png**

![B_30kN_displacement.png](../assets/readme/frame--B_30kN_displacement.png)

**B_30kN_energy.png**

![B_30kN_energy.png](../assets/readme/frame--B_30kN_energy.png)

**B_30kN_interstory.png**

![B_30kN_interstory.png](../assets/readme/frame--B_30kN_interstory.png)

**B_30kN_stress.png**

![B_30kN_stress.png](../assets/readme/frame--B_30kN_stress.png)

**B_30kN_velocity.png**

![B_30kN_velocity.png](../assets/readme/frame--B_30kN_velocity.png)

**AB_top_comparison.png**

![AB_top_comparison.png](../assets/readme/frame--AB_top_comparison.png)

**load_pulse.png**

![load_pulse.png](../assets/readme/frame--load_pulse.png)

**mesh_sensitivity.png**

![mesh_sensitivity.png](../assets/readme/frame--mesh_sensitivity.png)

**time_sensitivity.png**

![time_sensitivity.png](../assets/readme/frame--time_sensitivity.png)

</details>

<a id="sphere-impact"></a>

### Abaqus/Explicit · 球撞板 / Abaqus/Explicit · Sphere impact

板件真实位移/应力场；从原始ODB提取，未使用浏览器合成接触动画。

Actual plate ODB fields; synthetic browser contact animation is not used.

证据标签 / Evidence label: `saved-solve`。源归档记录 / Source record: `assets/readme/sphere-impact-record.json`。

![Abaqus/Explicit · 球撞板](../assets/readme/sphere-impact-result.png)

本图只展示保存的工件/板件场，未重建刀具、切屑、接触体或材料去除动画；求解结束不等同于冲击/加工机制得到实验验证。Saved workpiece/plate field only: no reconstructed tool, chips, contact body, or removal animation; completion does not establish experimental validation.

<a id="cutting"></a>

### Abaqus/Explicit · 正交切削算例 / Abaqus/Explicit · Orthogonal cutting

真实保存的工件场结果；展示范围不等同于切屑分离或切削模型精度验证。

Saved workpiece fields; chip separation and cutting accuracy are not certified.

证据标签 / Evidence label: `saved-solve`。源归档记录 / Source record: `assets/readme/cutting-record.json`。

![Abaqus/Explicit · 正交切削算例](../assets/readme/cutting-result.png)

本图只展示保存的工件/板件场，未重建刀具、切屑、接触体或材料去除动画；求解结束不等同于冲击/加工机制得到实验验证。Saved workpiece/plate field only: no reconstructed tool, chips, contact body, or removal animation; completion does not establish experimental validation.

<a id="milling"></a>

### Abaqus/Explicit · 三维铣削载荷响应 / Abaqus/Explicit · Milling load response

真实工件ODB应力；不包含浏览器刀具/切屑装饰，不宣称材料去除验证。

Actual workpiece ODB stress; no decorative tool/chips or material-removal claim.

证据标签 / Evidence label: `saved-solve`。源归档记录 / Source record: `assets/readme/milling-record.json`。

![Abaqus/Explicit · 三维铣削载荷响应](../assets/readme/milling-result.png)

本图只展示保存的工件/板件场，未重建刀具、切屑、接触体或材料去除动画；求解结束不等同于冲击/加工机制得到实验验证。Saved workpiece/plate field only: no reconstructed tool, chips, contact body, or removal animation; completion does not establish experimental validation.

<a id="bullet-impact"></a>

### Abaqus/Explicit · 弹丸冲击板件 / Abaqus/Explicit · Projectile/plate impact

真实板件应力场快照；求解完成不等于穿透、失效或防护性能获验证。

Actual plate stress snapshot; no certification of penetration, failure, or protection.

证据标签 / Evidence label: `saved-solve`。源归档记录 / Source record: `assets/readme/bullet-impact-record.json`。

![Abaqus/Explicit · 弹丸冲击板件](../assets/readme/bullet-impact-result.png)

本图只展示保存的工件/板件场，未重建刀具、切屑、接触体或材料去除动画；求解结束不等同于冲击/加工机制得到实验验证。Saved workpiece/plate field only: no reconstructed tool, chips, contact body, or removal animation; completion does not establish experimental validation.

## 流体流动 / Fluid flow

<a id="elbow"></a>

### Fluent · 90°弯管层流 / Fluent · Laminar 90° elbow

Re≈498；细网格全管静压降2.93381 Pa。场数据本地插值绘图。

Re≈498; fine full-pipe static drop=2.93381 Pa. Plotted solver field exports.

证据标签 / Evidence label: `saved-solve`。源归档记录 / Source record: `runs/elbow90_water_20261017/REPORT.md`。

![Fluent · 90°弯管层流](../assets/readme/elbow-result.png)

<details>
<summary>展开其余 4 张结果与校核图 / More result and check images</summary>

**convergence.png**

![convergence.png](../assets/readme/elbow--convergence.png)

**velocity_pressure.png**

![velocity_pressure.png](../assets/readme/elbow--velocity_pressure.png)

**velocity_profiles.png**

![velocity_profiles.png](../assets/readme/elbow--velocity_profiles.png)

**wall_shear.png**

![wall_shear.png](../assets/readme/elbow--wall_shear.png)

</details>

## 电磁场与电路 / Electromagnetics and circuits

<a id="maxwell"></a>

### Maxwell 3D · 旋转电磁执行器 / Maxwell 3D · Rotational actuator

0/10/20/30°静磁位置扫描；磁场、转矩及表观电感。非机械运动仿真。

0/10/20/30° magnetostatic sweep; fields, torque, apparent inductance; no motion solve.

证据标签 / Evidence label: `saved-solve`。源归档记录 / Source record: `MCP/Ansys/AEDT MCP/test-artifacts/rotational-actuator-20261001-1790841378441/中文验证报告.md`。

![Maxwell 3D · 旋转电磁执行器](../assets/readme/maxwell--B_midplane_30.png)

<details>
<summary>展开其余 11 张结果与校核图 / More result and check images</summary>

**B_corner_hotspots.png**

![B_corner_hotspots.png](../assets/readme/maxwell--B_corner_hotspots.png)

**B_midplane_0.png**

![B_midplane_0.png](../assets/readme/maxwell--B_midplane_0.png)

**B_surface_hotspots.png**

![B_surface_hotspots.png](../assets/readme/maxwell--B_surface_hotspots.png)

**B_topplane_0.png**

![B_topplane_0.png](../assets/readme/maxwell--B_topplane_0.png)

**B_topplane_30.png**

![B_topplane_30.png](../assets/readme/maxwell--B_topplane_30.png)

**B_iron_0.jpg**

![B_iron_0.jpg](../assets/readme/maxwell--B_iron_0.jpg)

**B_iron_30.jpg**

![B_iron_30.jpg](../assets/readme/maxwell--B_iron_30.jpg)

**torque_angle.png**

![torque_angle.png](../assets/readme/maxwell--torque_angle.png)

**mutual_inductance_angle.png**

![mutual_inductance_angle.png](../assets/readme/maxwell--mutual_inductance_angle.png)

**self_inductance_angle.png**

![self_inductance_angle.png](../assets/readme/maxwell--self_inductance_angle.png)

**geometry_view.jpg**

![geometry_view.jpg](../assets/readme/maxwell--geometry_view.jpg)

</details>

<a id="cst"></a>

### CST Design Studio · 电路S参数 / CST Design Studio · Circuit S-parameters

1–10 GHz、91频点；由实际S21导出数据绘图，不是三维屏蔽效能。

91 points over 1–10 GHz, from saved S21; not 3D shielding effectiveness.

证据标签 / Evidence label: `saved-solve`。源归档记录 / Source record: `MCP/CST/examples/design_studio_cosim_demo_run/fss_rlc_diode_schematic_demo_1783569136/Result/DS/Model.log`。

![CST Design Studio · 电路S参数](../assets/readme/cst-sparameters.png)

## 开源多物理场基准 / Open-source multiphysics benchmarks

<a id="fep-steady"></a>

### Elmer · 立方体稳态导热 / Elmer · Steady heat cube

已归档基准指标：Tmid≈350.270 K；图由结果清单绘制。

Archived benchmark Tmid≈350.270 K; plotted from the result manifest.

证据标签 / Evidence label: `saved-solve`。源归档记录 / Source record: `MCP/FEP-Agent-Hub/examples/heat-conduction-cube/result_manifest.json`。

![Elmer · 立方体稳态导热](../assets/readme/fep-steady.png)

此处只绘制归档标量/历程，未从缺失的VTU文件重建场图。基准假设、离散误差与专业复核范围见原目录README和报告。Only archived scalars/histories are plotted; missing VTU fields are not reconstructed. See the source benchmark documentation for assumptions and validation limits.

<a id="fep-transient"></a>

### Elmer · 真实瞬态导热 / Elmer · Transient heat conduction

20个BDF1物理时间步；20 s中点温度349.643 K。

20 BDF1 steps; midpoint=349.643 K at 20 s; a physical transient.

证据标签 / Evidence label: `saved-solve`。源归档记录 / Source record: `MCP/FEP-Agent-Hub/examples/transient-heat-cube/transient_heat_metrics.json`。

![Elmer · 真实瞬态导热](../assets/readme/fep-transient.png)

此处只绘制归档标量/历程，未从缺失的VTU文件重建场图。基准假设、离散误差与专业复核范围见原目录README和报告。Only archived scalars/histories are plotted; missing VTU fields are not reconstructed. See the source benchmark documentation for assumptions and validation limits.

<a id="fep-channel"></a>

### Elmer · 平面通道层流 / Elmer · Planar laminar channel

Re=100；实际平均速度0.0492233 m/s；与Poiseuille基准比对。

Re=100; measured mean speed=0.0492233 m/s; Poiseuille comparison.

证据标签 / Evidence label: `saved-solve`。源归档记录 / Source record: `MCP/FEP-Agent-Hub/examples/laminar-channel-flow-2d/flow_metrics.json`。

![Elmer · 平面通道层流](../assets/readme/fep-channel.png)

此处只绘制归档标量/历程，未从缺失的VTU文件重建场图。基准假设、离散误差与专业复核范围见原目录README和报告。Only archived scalars/histories are plotted; missing VTU fields are not reconstructed. See the source benchmark documentation for assumptions and validation limits.

<a id="fep-transformer"></a>

### Elmer · 二维谐波变压器 / Elmer · 2D harmonic transformer

50 Hz开路次级感应电压；基线、半电流与细网格对比。

50 Hz open-circuit induction; baseline, half-current, and fine-mesh comparison.

证据标签 / Evidence label: `saved-solve`。源归档记录 / Source record: `MCP/FEP-Agent-Hub/examples/transformer-induction-2d/induction_metrics.json`。

![Elmer · 二维谐波变压器](../assets/readme/fep-transformer.png)

此处只绘制归档标量/历程，未从缺失的VTU文件重建场图。基准假设、离散误差与专业复核范围见原目录README和报告。Only archived scalars/histories are plotted; missing VTU fields are not reconstructed. See the source benchmark documentation for assumptions and validation limits.

<a id="fep-lenz"></a>

### Elmer · 楞次定律瞬态涡流 / Elmer · Transient eddy currents

40步真实瞬态，半时间步/细网格专项指标；图为归档敏感性值。

40-step transient; archived time/mesh sensitivity metrics, not reconstructed fields.

证据标签 / Evidence label: `saved-solve`。源归档记录 / Source record: `MCP/FEP-Agent-Hub/examples/lenz-law-transient-eddy/expected_metrics.json`。

![Elmer · 楞次定律瞬态涡流](../assets/readme/fep-lenz.png)

此处只绘制归档标量/历程，未从缺失的VTU文件重建场图。基准假设、离散误差与专业复核范围见原目录README和报告。Only archived scalars/histories are plotted; missing VTU fields are not reconstructed. See the source benchmark documentation for assumptions and validation limits.

<a id="fep-beam"></a>

### Elmer · 简支梁应力应变 / Elmer · Simply supported beam

10个独立准静态载荷级；满载跨中挠度0.633804 mm；不是结构动力学。

Ten independent static load levels; full-load midspan deflection=0.633804 mm.

证据标签 / Evidence label: `saved-solve`。源归档记录 / Source record: `MCP/FEP-Agent-Hub/examples/simply-supported-beam-2d/beam_metrics.json`。

![Elmer · 简支梁应力应变](../assets/readme/fep-beam.png)

此处只绘制归档标量/历程，未从缺失的VTU文件重建场图。基准假设、离散误差与专业复核范围见原目录README和报告。Only archived scalars/histories are plotted; missing VTU fields are not reconstructed. See the source benchmark documentation for assumptions and validation limits.

## 求解器基准与能量历程 / Solver benchmarks and energy histories

<a id="radioss-axial"></a>

### Radioss · 实体轴向碰撞 / Radioss · Axial solid collision

原生Engine日志正常结束；展示内能、平动动能与带符号能量误差，不据此认证工程精度。

Normal engine termination; printed internal/kinetic energy and signed error; accuracy not certified.

证据标签 / Evidence label: `saved-solve`。源归档记录 / Source record: `MCP/HyperWorks/workspace/projects/project_20260721_154328_e76033/runs/radioss_20260721_154352_8a370d/input/solid_axial_collision_0001.out`。

![Radioss · 实体轴向碰撞](../assets/readme/radioss-axial.png)

<a id="radioss-drop"></a>

### Radioss · 落锤算例 / Radioss · Drop-weight benchmark

原生Engine日志正常结束；展示内能、平动动能与带符号能量误差，不据此认证工程精度。

Normal engine termination; printed internal/kinetic energy and signed error; accuracy not certified.

证据标签 / Evidence label: `saved-solve`。源归档记录 / Source record: `MCP/HyperWorks/workspace/projects/project_20260721_154328_9ab16c/runs/radioss_20260721_154345_b1c162/input/drop_weight_0001.out`。

![Radioss · 落锤算例](../assets/readme/radioss-drop.png)

<a id="radioss-plate"></a>

### Radioss · 板件冲击 / Radioss · Plate impact

原生Engine日志正常结束；展示内能、平动动能与带符号能量误差，不据此认证工程精度。

Normal engine termination; printed internal/kinetic energy and signed error; accuracy not certified.

证据标签 / Evidence label: `saved-solve`。源归档记录 / Source record: `MCP/HyperWorks/workspace/projects/project_20260721_154328_11575f/runs/radioss_20260721_154349_c905c0/input/plate_impact_0001.out`。

![Radioss · 板件冲击](../assets/readme/radioss-plate.png)

<a id="radioss-block"></a>

### Radioss · 块体碰撞 / Radioss · Block impact

原生Engine日志正常结束；展示内能、平动动能与带符号能量误差，不据此认证工程精度。

Normal engine termination; printed internal/kinetic energy and signed error; accuracy not certified.

证据标签 / Evidence label: `saved-solve`。源归档记录 / Source record: `MCP/HyperWorks/workspace/projects/project_20260721_101928_885d35/runs/radioss_20260721_102312_a2454e/input/v090_radioss_block_impact_0001.out`。

![Radioss · 块体碰撞](../assets/readme/radioss-block.png)

<a id="optistruct-modal"></a>

### OptiStruct · 固有频率谱 / OptiStruct · Frequency spectrum

实际完成日志中的六阶频率，未补造振型。

Six frequencies from the completed native run; mode shapes are not reconstructed.

证据标签 / Evidence label: `saved-solve`。源归档记录 / Source record: `MCP/HyperWorks/workspace/projects/project_20260721_153839_384cf8/runs/optistruct_20260721_153906_55c134/input/modal.out`。

![OptiStruct · 固有频率谱](../assets/readme/optistruct-modal.png)

<a id="optistruct-buckling"></a>

### OptiStruct · 线性屈曲特征值 / OptiStruct · Linear buckling eigenvalues

保留原始负特征值符号，需结合预载方向解释，不能直接作为许用载荷。

Original negative eigenvalue signs retained; interpret with preload direction, not as allowable loads.

证据标签 / Evidence label: `saved-solve`。源归档记录 / Source record: `MCP/HyperWorks/workspace/projects/project_20260721_155423_a79ec3/runs/optistruct_20260721_155439_597f01/input/buckling_clean.out`。

![OptiStruct · 线性屈曲特征值](../assets/readme/optistruct-buckling.png)

## 历史后处理归档 / Historical postprocessing exports

<a id="hyperview-bracket"></a>

### HyperView · 1000 N L形支架归档 / HyperView · Archived 1000 N L-bracket

已有H3D与云图；未在本轮找到对应完成日志，按历史后处理结果展示。

Saved H3D and contours; matching completion logs were not located in this review.

证据标签 / Evidence label: `archived-export`。源归档记录 / Source record: `MCP/HyperWorks/workspace/L_bracket_static_1000N.h3d`。

![HyperView · 1000 N L形支架归档](../assets/readme/hyperview-bracket--stress_vonmises.png)

<details>
<summary>展开其余 9 张结果与校核图 / More result and check images</summary>

**displacement_mag.png**

![displacement_mag.png](../assets/readme/hyperview-bracket--displacement_mag.png)

**displacement_x.png**

![displacement_x.png](../assets/readme/hyperview-bracket--displacement_x.png)

**displacement_y.png**

![displacement_y.png](../assets/readme/hyperview-bracket--displacement_y.png)

**displacement_z.png**

![displacement_z.png](../assets/readme/hyperview-bracket--displacement_z.png)

**stress_principal_max.png**

![stress_principal_max.png](../assets/readme/hyperview-bracket--stress_principal_max.png)

**stress_principal_min.png**

![stress_principal_min.png](../assets/readme/hyperview-bracket--stress_principal_min.png)

**spcforce_x.png**

![spcforce_x.png](../assets/readme/hyperview-bracket--spcforce_x.png)

**hole1_spcforce_x_mean.png**

![hole1_spcforce_x_mean.png](../assets/readme/hyperview-bracket--hole1_spcforce_x_mean.png)

**hole2_spcforce_x_mean.png**

![hole2_spcforce_x_mean.png](../assets/readme/hyperview-bracket--hole2_spcforce_x_mean.png)

</details>

<a id="calculix-static"></a>

### CalculiX · 悬臂梁静力归档 / CalculiX · Archived static beam

从已保存result_mesh导出绘制；原始ccx日志未随附，本次不追加收敛认证。

Rendered saved result_mesh export; original ccx logs are not bundled; no added convergence claim.

证据标签 / Evidence label: `archived-export`。源归档记录 / Source record: `models/text-to-cae-calculix-cantilever/result_mesh.json`。

![CalculiX · 悬臂梁静力归档](../assets/readme/calculix-static.png)

<a id="calculix-modal"></a>

### CalculiX · 第一阶振型归档 / CalculiX · Archived first mode

从已保存result_mesh导出绘制；原始ccx日志未随附，本次不追加收敛认证。

Rendered saved result_mesh export; original ccx logs are not bundled; no added convergence claim.

证据标签 / Evidence label: `archived-export`。源归档记录 / Source record: `models/text-to-cae-calculix-modal/result_mesh.json`。

![CalculiX · 第一阶振型归档](../assets/readme/calculix-modal.png)

## 校准与技术验收结果 / Calibration and technical acceptance

<a id="gear-calibration"></a>

### Mechanical · 齿轮接触校准工况 / Mechanical · Gear contact calibration

真实无摩擦校准解；未达到目标扭矩，不代表最终μ=0.08工况。

Actual frictionless calibration; target torque not reached; not the final μ=0.08 case.

证据标签 / Evidence label: `partial-calibration`。源归档记录 / Source record: `viewer/dist/ansys-gear-contact/index.html`。

![Mechanical · 齿轮接触校准工况](../assets/readme/gear-calibration--contact_pressure.png)

<details>
<summary>展开其余 3 张结果与校核图 / More result and check images</summary>

**contact_status.png**

![contact_status.png](../assets/readme/gear-calibration--contact_status.png)

**equivalent_stress.png**

![equivalent_stress.png](../assets/readme/gear-calibration--equivalent_stress.png)

**total_deformation.png**

![total_deformation.png](../assets/readme/gear-calibration--total_deformation.png)

</details>

<a id="icepak-smoke"></a>

### Icepak · 热块接口验收算例 / Icepak · Heat-block interface acceptance

接口验收保存解，温度约571.5 °C；仅展示技术流程，不是合格散热设计。

Saved acceptance-test solution, ≈571.5 °C; a technical smoke test, not a qualified thermal design.

证据标签 / Evidence label: `technical-smoke`。源归档记录 / Source record: `MCP/Ansys/AEDT MCP/test-artifacts/IcepakMcpAcceptance/20260905-134319/result.json`。

![Icepak · 热块接口验收算例](../assets/readme/icepak-smoke--temperature-field.jpg)

## 未作为实算图展示的内容 / Items not represented as solved fields

- F-22外流与齿轮浏览器动态预览由确定性生成器产生；不作为Fluent/Abaqus实算结果。F-22 flow and animated gear preview payloads are deterministic visualizations, not verified solver fields.
- ANSA失败几何、漏约束/零响应试算、空白或遮挡截图、锁屏图，以及重复报告页未收入。Failed geometry, rejected zero-response runs, blocked screenshots, and duplicate report-page images are excluded.
- LAMMPS/OVITO等仅有接口或脚本、未找到可对应已完成求解的图像/数值记录时，不补造结果。Adapters without matching solved data or images are not assigned invented results.

## 来源清单 / Provenance manifest

[provenance.json](../assets/readme/provenance.json)逐项记录图片和源数据的SHA-256、归档相对路径及绘制方法。源路径是原始本地归档标识，不代表这些大型求解文件已经上传。The manifest records hashes, archive-relative paths, and transformations. Original solver archives remain separate; a hash establishes correspondence when an original is available and does not validate the physics.
