# 损伤与裂纹推进 / Damage and crack advance

This is a curated replay of a real Peridigm run, not a browser solve. / 这是实际求解结果的精选回放，网页不会重新求解。

- Profile / 模板: `notched-tension-damage-v1`
- Material points / 材料点: 3200
- Displayed native frames / 真实展示帧: 31; no interpolation / 未插值。
- Units and scope / 单位与能力边界: see `case.json` and `validation.json`.
- Run identity and original native-result hashes / 来源与原生结果摘要: `demo.json`.
- Progressive confirmation trace / 渐进确认轨迹: `workflow.json`, with the private request omitted.

From `viewer/`, install the locked dependencies with `npm ci`, then `npm run dev`. Open `/peridigm.html?demo=fracture` at the printed loopback address. No Peridigm installation or SSH connection is needed for replay. To solve again, use the separately configured CLI/MCP workflow in [Peridigm](../../MCP/Peridigm/README.md).

在 `viewer/` 中安装依赖后启动网页，打开 `/peridigm.html?demo=fracture`。回放不依赖求解器或SSH；重新计算需按模块说明配置独立环境。字段均为实际材料点结果，不虚构有限元连通或裂纹面。

Synthetic thin-layer dynamic fracture demonstration with 3D Elastic constitutive law, not plane-stress calibration, a converged 3D specimen or an experimental prediction. No contact. Only the exact reviewed profile is supported.

Full native results, solver binaries, machine configuration, original private requests and worker logs are intentionally excluded from this redistributable fixture. This fixture is covered by the repository license; solver/template attribution remains in [THIRD_PARTY_NOTICES](../../MCP/Peridigm/THIRD_PARTY_NOTICES.md).
