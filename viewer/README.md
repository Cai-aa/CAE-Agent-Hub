# Text to CAE Viewer

This is the browser viewer for the standalone Text-to-CAE workspace.

```powershell
npm.cmd run dev
npm.cmd run build
```

The app defaults to the CAE workspace and talks to local endpoints under `/__cae/*` provided by `vite.config.mjs`.

## Agentic PD replay entry

Open `/peridigm.html` after `npm ci` and `npm run dev`. Query `?demo=elastic` or `?demo=fracture` loads a curated, verified dataset from `models/peridigm-*`; no SSH, solver or private runtime files are required. `npm run build` emits these imports as static assets, so the demos also work when serving the build directory with a plain loopback HTTP server. The original index entry is retained.

`?result=/run/result_mesh.json` remains supported for a project-local, read-only run preview; loading a local result file is also supported. Demo replay never invokes a model or a solver. The shared viewer renders material points without invented FE elements and distinguishes Damage from displacement. See [Peridigm demo guide](../MCP/Peridigm/DEMO.md).

### Portable static preview / 跨平台静态预览

After building, run the following from `viewer/` (use `python3` if your platform requires it):

```sh
python ../MCP/Peridigm/scripts/serve_demos.py --directory dist --port 4179
```

Open `http://127.0.0.1:4179/peridigm.html`. The standard-library helper is read-only, loopback-only, and supplies correct JavaScript/JSON MIME types on Windows as well as Linux. It never starts a model or solver and disables stale local-preview caching. Ctrl+C stops this foreground preview.
