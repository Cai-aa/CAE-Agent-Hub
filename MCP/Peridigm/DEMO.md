# Agentic PD demos / 演示与来源

## View a recorded result / 查看结果回放

```sh
cd viewer
npm ci
npm run dev
```

Open the printed loopback address with `/peridigm.html`. `/peridigm.html?demo=elastic` and `/peridigm.html?demo=fracture` load the packaged fixtures. For a static build, run `npm run build` and serve `viewer/dist` (or your chosen output directory) with any ordinary loopback static server. Both dataset URLs are bundled: no `/__cae` API, SSH or Peridigm is needed for replay.

网页明确显示“已计算结果回放”。可播放/暂停、选择真实保存帧、切换Damage/位移，查看参数、验证摘要、真实曲线及文件摘要。没有浏览器求解按钮，也没有假装已连接的LLM。要重新计算，按模块README配置独立运行环境并使用CLI/MCP。

| Fixture / 样本 | Provenance / 来源 | Verified behavior / 已验证 | Boundary / 边界 |
| --- | --- | --- | --- |
| [Elastic](../../models/peridigm-elastic) | Actual run `a24c5dcea9304f09`, source `Compression_2x1x1` profile | 2 points, 6 frames; displacement/velocity/force/dilatation differences vs gold are 0; independent oscillator displacement error 0.2427% < 0.5% | Elastic code verification; not a resolved specimen, fracture or calibrated strength |
| [Damage/fracture](../../models/peridigm-notched-tension) | Actual run `544063c262d84fee`, exact synthetic `notched-tension-damage-v1` profile | 3,200 points; 601 native states reduced to 31 actual display states; 6,661 new failed pairs; reconstructed Damage error 0; connected front indicator advances 12.5mm | Single layer with 3D constitutive law; no experimental calibration, spatial convergence or exact crack surface |

The fracture time-step comparison is recorded in its `time-step-check.json`: half-step run `8988e23a83c441f9`, 6,700 new failed pairs, same final indicator, maximum common-time indicator difference 0.5mm. It is descriptive sensitivity, not a formal convergence or accuracy certification. Full energy/work balance and MPI fracture remain unverified.

## Files and privacy / 文件与隐私

Each fixture includes `result_mesh.json`, canonical `input.yaml` (and fracture `points.txt`), public `case.json`, `validation.json`, `response.csv`, a curated `workflow.json`, `demo.json` provenance and a file-hash `manifest.json`. Native values and selected frames are retained without fabricated interpolation. `case.json` is a public parameter subset, not a replacement for the source run's full frozen specification.

Raw natural-language requests, credentials, machine paths, process IDs, worker logs, solver binaries and full native output files are excluded. The trace marks the real source operator as `codex_operator`; it is not a human-user study. The manifest identifies the public fixture files; native result hashes in `demo.json` identify separately retained source outputs.

Full source-run evidence remains in the independently configured project's `runs/` directory. A successful recorded demo does not mean an arbitrary Peridigm installation, constitutive law, mesh or case is supported. In particular the inspected build requires separate Critical Stretch tension/compression parameters. Read the [fracture reference](../../Skill/peridigm/peridigm-evidence-fracture/references/fracture.md) and [third-party notices](THIRD_PARTY_NOTICES.md).

## Regenerate from a verified run / 从已验证运行重新导出

```sh
python MCP/Peridigm/scripts/export_demo.py --run /path/to/project/runs/RUN_ID --out models/NEW_DEMO_DIRECTORY
```

The exporter requires a new output directory and checks completed state, frozen-spec/input/native-result identity and the validation record before copying an allowlist of public files. It does not solve again and cannot turn an unverified output into a passed fixture. Register a new curated dataset in the Peridigm viewer only after reviewing its physics and public contents.

### Portable static preview / 跨平台静态预览

After building, run the following from `viewer/` (use `python3` if your platform requires it):

```sh
python ../MCP/Peridigm/scripts/serve_demos.py --directory dist --port 4179
```

Open `http://127.0.0.1:4179/peridigm.html`. The standard-library helper is read-only, loopback-only, and supplies correct JavaScript/JSON MIME types on Windows as well as Linux. It never starts a model or solver and disables stale local-preview caching. Ctrl+C stops this foreground preview.
