"""Build a relocatable native ANSA Plugins package for an installed MCP bridge.

The package includes a versioned runtime, no credentials. The installed entry
is used only to locate/validate the existing authenticated configuration.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import zipfile
from pathlib import Path

from build_ansa_plugin import MARKER, TEMPLATE


HERE = Path(__file__).resolve().parent
PLUGIN_NAME = "ANSA_MCP_Bridge"
VERSION = "0.5.0"


def build_package(bridge_entry: Path | None, output: Path, ansa_launcher: Path | None = None,
                  minimum_ansa_version: str = "25.0.0") -> dict:
    import re
    if not re.fullmatch(r"\d+\.\d+\.\d+", minimum_ansa_version):
        raise ValueError("minimum ANSA version must be major.minor.patch")
    if bridge_entry is not None:
        bridge_entry = bridge_entry.resolve(strict=True)
        if bridge_entry.name != "ansa_mcp_plugin.py" or not bridge_entry.is_file():
            raise ValueError("bridge entry must be an existing ansa_mcp_plugin.py")
    output = output.resolve()
    if output.exists():
        raise FileExistsError("package output already exists; refusing to overwrite")
    descriptor = TEMPLATE.read_text(encoding="utf-8")
    descriptor = descriptor.replace('minHostApplicationVersion = "v25.0.0"',
                                    'minHostApplicationVersion = "v' + minimum_ansa_version + '"')
    if descriptor.count(MARKER) != 1:
        raise ValueError("descriptor template must contain exactly one entry marker")
    descriptor = descriptor.replace(
        MARKER,
        'os.path.join(os.path.dirname(os.path.abspath(__file__)), '
        '"ANSA_MCP_Bridge", "src", "ansa_mcp_ui.py")',
    )
    wrapper = (HERE / "plugin" / "ansa_mcp_ui.py.in").read_text(encoding="utf-8")
    wrapper = wrapper.replace("__ANSA_MCP_BRIDGE_ENTRY__", repr(str(bridge_entry)) if bridge_entry else "None")
    compile(descriptor, "ANSA_MCP_Bridge.ppl", "exec")
    # ANSA's loader can prefix generated code before this entry.
    compile("_ansa_generated_prefix = True\n" + wrapper, "ansa_mcp_ui.py", "exec")
    files = {
        "ANSA_MCP_Bridge.ppl": descriptor,
        "ANSA_MCP_Bridge/src/__init__.py": '"""ANSA MCP native plugin UI package."""\n',
        "ANSA_MCP_Bridge/src/ansa_mcp_ui.py": wrapper,
        "ANSA_MCP_Bridge/docs/README.zh-CN.md": (HERE / "plugin" / "README.zh-CN.md").read_text(encoding="utf-8"),
        "ANSA_MCP_Bridge/docs/README.md": (HERE / "plugin" / "README.md").read_text(encoding="utf-8"),
        "ANSA_MCP_Bridge/docs/GENERAL_OPERATIONS.md": (HERE / "GENERAL_OPERATIONS.md").read_text(encoding="utf-8"),
        "ANSA_MCP_Bridge/docs/ENGINEERING_OPERATIONS.md": (HERE / "ENGINEERING_OPERATIONS.md").read_text(encoding="utf-8"),
    }
    runtime_source = HERE / "ansa_plugin" / "ansa_mcp_bridge"
    runtime_modules = []
    for source in sorted(runtime_source.glob("*.py")):
        relative = "ansa_mcp_bridge/" + source.name
        content = source.read_text(encoding="utf-8")
        compile(content, relative, "exec")
        files["ANSA_MCP_Bridge/src/" + relative] = content
        runtime_modules.append({"path": relative, "compile": False})
    package_metadata = {
        "ansa_metadata": {
            "archive_name": f"{PLUGIN_NAME}-{VERSION}.bpkg",
            "plugin_name": PLUGIN_NAME,
            "main_module": "ansa_mcp_ui.py",
            "module_paths": [
                {"path": "__init__.py", "compile": False},
                {"path": "ansa_mcp_ui.py", "compile": False},
                *runtime_modules,
            ],
        }
    }
    files["packager_metadata.json"] = json.dumps(package_metadata, indent=2)
    output.mkdir(parents=True)
    hashes = {}
    for relative, content in files.items():
        path = output / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        data = content.encode("utf-8")
        path.write_bytes(data)
        hashes[relative] = hashlib.sha256(data).hexdigest()
    manifest = {
        "name": PLUGIN_NAME, "version": VERSION,
        "format": "ANSA native plugin directory",
        "bridge_entry": str(bridge_entry) if bridge_entry else None,
        "portable_configuration": bridge_entry is None,
        "minimum_ansa_version": minimum_ansa_version,
        "minimum_embedded_python": "3.9",
        "compatibility_claim": "Runtime capability probes; other host versions unverified. Build vendor .bpkg on target ANSA when required.",
        "entry": "ANSA_MCP_Bridge.ppl",
        "files_sha256": hashes,
        "credentials_included": False,
        "runtime_bundled": True,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    archive = output / f"{PLUGIN_NAME}-{VERSION}.zip"
    with zipfile.ZipFile(archive, "x", zipfile.ZIP_DEFLATED) as bundle:
        for relative in sorted([*files, "manifest.json"]):
            bundle.write(output / relative, relative)
    result = {"directory": str(output), "archive": str(archive), "manifest": manifest}
    if ansa_launcher is not None:
        launcher = ansa_launcher.resolve(strict=True)
        api = launcher.parent / "config/plugins/PackagerInstaller/docs/no_gui_execution.py"
        if not api.is_file():
            raise FileNotFoundError("Official BETA Packager Installer API not found beside launcher")
        env = dict(os.environ)
        env["ANSA_MCP_NATIVE_PACKAGE_DIR"] = str(output)
        env["ANSA_MCP_PACKAGER_API"] = str(api)
        with (output / "packager.log").open("wb") as log:
            completed = subprocess.run(
                [str(launcher), "-nogui", "-exec", "load_script:" + str(HERE / "ansa_build_bpkg.py")],
                cwd=output, env=env, stdin=subprocess.DEVNULL, stdout=log,
                stderr=subprocess.STDOUT, timeout=120, check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        receipt_path = output / "bpkg_build_report.json"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8")) if receipt_path.is_file() else {}
        if completed.returncode != 0 or not receipt.get("ok"):
            raise RuntimeError("Official packager failed; see packager.log and bpkg_build_report.json")
        bpkg = output / f"{PLUGIN_NAME}-{VERSION}.bpkg"
        with zipfile.ZipFile(bpkg) as bundle:
            if bundle.testzip() is not None:
                raise RuntimeError("BETA package ZIP integrity check failed")
            required = {"metadata.json", "ANSA_MCP_Bridge.ppl",
                        "ANSA_MCP_Bridge/src/ANSA_MCP_Bridge.py",
                        "ANSA_MCP_Bridge/src/ANSA_MCP_Bridge.bpkgo.zip"}
            if not required.issubset(bundle.namelist()):
                raise RuntimeError("BETA package is missing required plugin files")
        result["bpkg"] = str(bpkg)
        result["bpkg_sha256"] = hashlib.sha256(bpkg.read_bytes()).hexdigest()
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bridge-entry", type=Path, help="Optional machine-specific config locator; omit for redistributable package")
    parser.add_argument("--minimum-ansa-version", default="25.0.0", help="Descriptor gate only, not compatibility certification")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--ansa-launcher", type=Path, help="Optional ansa64.bat; builds the official .bpkg too")
    args = parser.parse_args()
    print(json.dumps(build_package(args.bridge_entry, args.output, args.ansa_launcher, args.minimum_ansa_version), indent=2))


if __name__ == "__main__":
    main()
