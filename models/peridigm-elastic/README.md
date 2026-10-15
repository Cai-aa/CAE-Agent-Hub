# 弹性代码验证 / Elastic verification

This is a curated replay of a real Peridigm run, not a browser solve. / 这是实际求解结果的精选回放，网页不会重新求解。

- Profile / 模板: `compression-two-point-v1`
- Material points / 材料点: 2
- Displayed native frames / 真实展示帧: 6; no interpolation / 未插值。
- Units and scope / 单位与能力边界: see `case.json` and `validation.json`.
- Run identity and original native-result hashes / 来源与原生结果摘要: `demo.json`.
- Progressive confirmation trace / 渐进确认轨迹: `workflow.json`, with the private request omitted.

From `viewer/`, install the locked dependencies with `npm ci`, then `npm run dev`. Open `/peridigm.html?demo=elastic` at the printed loopback address. No Peridigm installation or SSH connection is needed for replay. To solve again, use the separately configured CLI/MCP workflow in [Peridigm](../../MCP/Peridigm/README.md).

在 `viewer/` 中安装依赖后启动网页，打开 `/peridigm.html?demo=elastic`。回放不依赖求解器或SSH；重新计算需按模块说明配置独立环境。字段均为实际材料点结果，不虚构有限元连通或裂纹面。

Synthetic elastic dynamics verification, not a resolved 3D specimen, fracture, calibrated material or engineering strength prediction. No contact, damage or arbitrary geometry is supported in v0.1.

Full native results, solver binaries, machine configuration, original private requests and worker logs are intentionally excluded from this redistributable fixture. This fixture is covered by the repository license; solver/template attribution remains in [THIRD_PARTY_NOTICES](../../MCP/Peridigm/THIRD_PARTY_NOTICES.md).
