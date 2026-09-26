# ANSA MCP Bridge 0.5.0 — general-purpose Windows runtime

See [setup and compatibility](GENERAL_OPERATIONS.md) and [engineering operations](ENGINEERING_OPERATIONS.md). Public
packages have no bridge_entry path; set ANSA_MCP_BRIDGE_CONFIG for both processes.
Restart both ANSA and MCP after upgrading to refresh the runtime and tool list.

This package bundles the runtime and adds Start / Status / Stop buttons to
ANSA's Plugins ribbon. It reuses the installed bridge's configuration and
authentication. No credentials are included and installation does not start the
bridge. Only machine-specific packages require keeping the installed entry
named by a non-null `bridge_entry` in `manifest.json`.

## Fixes

- Connection/session overview distinguishes a listening bridge from recent
  authenticated traffic; version, PID, deck, file and uptime are shown.
- History retains 100 requests with timing, bounded parameter/result summaries,
  errors, uncertain outcomes and cached replays. Python source is hashed only;
  arbitrary Python result payloads and credentials are not retained.
- Model snapshots compare node, element, face, property and material counts
  before/after mutations. Disable sampling for large models. Missing counts and
  changed database/deck contexts are never reported as zero deltas.
- Diagnostics offer session self-check, clipboard copy and unique JSON exports
  beneath the first allowed workspace's diagnostics directory.
- No pause, forced cancellation or undo is promised. Long GUI-thread calls can
  block panel painting; use short MCP steps. Counts and redraw success do not
  establish engineering validity. Review paths/parameters before sharing exports.
- Keep existing MCP registration/configuration. After upgrading, save your model
  and restart ANSA to discard cached Python modules. Installation does not start
  the listener. Existing authenticated bridge configuration remains required.

- The descriptor retains its metadata object in a global variable. ANSA 25.1.2
  `session.setPluginInfos` does not increase its Python reference count; a
  temporary object is freed too early.
- The native button entry has no future imports. It uses standard Python
  imports for the bridge, avoiding the future-import error produced by ANSA's
  generated script prefix.
- The descriptor locates its sibling source directory relatively, so the
  descriptor and its same-named directory can be moved together.

## Recommended: official BETA Package installation

1. Open **Development > BETA Packager Installer > Installer** in ANSA.
2. Select the released `ANSA_MCP_Bridge-0.5.0.bpkg`.
3. Choose **Your .BETA plugins directory** and finish installation.
4. Restart ANSA and use **Plugins > ANSA MCP > Start / Status / Stop**.

The official installer extracts the package and registers it with Plugin
Manager. The plugin entry loads on subsequent startups; the bridge itself
starts only when Start is pressed. If the current session has not refreshed
the entry, restart before overwriting the settings saved by the installer.

## Alternative: native directory package installation

Extract the complete ZIP into a permanent user-owned directory. Keep the `.ppl`
and `ANSA_MCP_Bridge` directory next to each other. Use Development > Plugin
Manager > Add to select the new descriptor,
enable Active, Apply, and save ANSA GUI Settings. Restart ANSA and check the
ANSA MCP group on the Plugins ribbon. Keep the files in place; repeated Load
Script is not required after successful persistent registration.

Start opens the bridge panel in the current ANSA session; Status reads its state;
Stop stops it. Start does not modify the model. Closing the panel also stops the
bridge. Do not reuse the old descriptor under `output/plugin_candidate`.

See the release validation report for test scope. Desktop installation is
identified by Plugins buttons and Runtime 0.5.0 in the panel; verify connectivity
with an authenticated request, not the label alone. History is in-memory
and resets on restart; export when needed. Count snapshots are not continuous
model synchronization: refresh after manual edits.
