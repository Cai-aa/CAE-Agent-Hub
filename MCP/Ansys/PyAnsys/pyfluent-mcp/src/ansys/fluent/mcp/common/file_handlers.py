# Copyright (C) 2026 Synopsys, Inc. and ANSYS, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Modular registry mapping file suffixes to product/component handlers.

Used by the ``read_file`` agent tool to:

1. Recognize a user-supplied filesystem path by suffix.
2. Probe the file (cheap, read-only) for product-relevant metadata, such
   as dimension and precision for a Fluent ``.cas.h5`` archive.
3. Decide which backend (PyFluent solver, Fluids One solve, …) and
   which launch options (precision, dimension, lightweight) to use.

Adding a new file type is a single registry call. See
:func:`register_handler`. The registry is intentionally tiny. Each
handler owns its own suffix list, candidate-product list, probe
function, and launch-argument builder.

Design constraints:

* No I/O at import time. All probing is lazy and read-only.
* Optional dependencies (``h5py``) are imported inside probe functions
  so the agent works even when the extra is not installed.
* Probes never write to the file, never lock it, and never modify the
  user's session.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
from pathlib import Path, PureWindowsPath
from typing import Any, Callable

logger = logging.getLogger("ansys.fluent.mcp.common.file_handlers")


# ---------------------------------------------------------------------------
# Cross-platform path normalization
# ---------------------------------------------------------------------------
#
# Every code snippet we build for Fluent contains a quoted file path:
#
#     session.settings.file.read_case(file_name="C:\foo\case.cas.h5")
#     session.settings.file.read_data(file_name="C:\foo\soln.dat.h5")
#
# A Windows raw path embedded in a single/double-quoted Python string is a
# trap: ``\n``, ``\t``, ``\f``, ``\b``, ``\v``, ``\0``, ``\r``, ``\u…``,
# ``\x…`` are all valid Python string-escape sequences, so a path like
# ``C:\foo\new\table.cas`` silently expands to ``C:\foo<newline>ew<TAB>able.cas``
# inside the generated source code and Fluent then can't find the file.
# Worst case the path looks plausible after the expansion and Fluent loads
# the WRONG file from the user's machine.
#
# The fix is universal: every path we inject into a snippet — and every
# path we hand to Fluent's settings API across an RPC boundary — must be
# converted to forward-slash POSIX form FIRST. Both Fluent on Windows
# and Fluent on Linux accept forward slashes in file paths, so we can
# normalize unconditionally; only backslashes are the danger.
#
# ``PureWindowsPath`` is used as the parser regardless of the host OS
# because it is the only one of the two ``pathlib`` engines that
# recognizes ``\`` as a separator. On POSIX, ``Path('C:\\foo')`` would
# leave the backslashes literal — that's correct for filesystem ops on
# Linux, but here we explicitly want to translate the Windows-flavored
# string that the authoring host may have produced (e.g. when the host runs on
# Linux but the Fluent solver lives on a Windows fileshare reached via
# a backslash UNC path).


def normalize_path_for_fluent(path: str | Path) -> str:
    r"""Return ``path`` as a forward-slash POSIX-style string.

    Cross-platform safe: works whether the input is a ``pathlib.Path``
    object, a Windows-style raw string (``"C:\\\\foo\\bar"``), a
    Windows-style forward-slash string (``"C:/foo/bar"``), or a POSIX
    path (``"/foo/bar"``). Output is safe to embed inside a Python
    source code snippet bound for Fluent — no Python string-escape
    pitfalls — and is accepted by Fluent's settings API on both
    Windows and Linux solver builds.

    Notable shapes preserved by the conversion:

    * Drive letters: ``C:\\foo`` → ``C:/foo``.
    * UNC paths: ``\\\\server\\share\\file`` → ``//server/share/file``.
    * Mixed separators: ``C:/foo\\bar`` → ``C:/foo/bar``.
    * No trailing slashes (matches Fluent's expected form).

    Why not ``str(path).replace('\\', '/')``? That works for the common
    case but leaves redundant separators and doesn't normalize mixed
    ``./``/``../`` segments. Routing through ``PureWindowsPath``
    handles those cases consistently. ``..`` resolution is left to the
    caller (we never want to silently rewrite ``..`` paths — the
    ``_validate_read_file_path`` guard rejects them outright).

    Parameters
    ----------
    path : str | Path
        Fluent object path or file-system path to inspect.

    Returns
    -------
    str
        String result produced by the function.
    """
    return PureWindowsPath(str(path)).as_posix()


# ---------------------------------------------------------------------------
# Public dataclasses
# ---------------------------------------------------------------------------


@dataclass
class FileProbe:
    """Result of probing a file for product-relevant metadata.

    Fields are deliberately ``Optional``. If a probe cannot determine
    a value (for example, because of an unreadable header or a missing optional dependency),
    the agent falls back to asking the user or to the backend default.
    """

    file_type: str  # human label, e.g. "Fluent case"
    suffix: str  # canonical suffix, e.g. ".cas.h5"
    dimension: int | None = None  # 2 or 3
    precision: str | None = None  # "single" or "double"
    is_lightweight: bool | None = None  # only meaningful for some files
    extra: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)


@dataclass
class FileHandler:
    """Describes one file type the agent can route to a backend."""

    name: str  # e.g. "fluent_case"
    suffixes: tuple[str, ...]  # ordered, longest-first preferred
    file_type: str  # human label
    candidate_products: tuple[str, ...]  # backend kinds, e.g. ("pyfluent","fluids_one")
    needs_mode_choice: bool  # ask lightweight vs full?
    probe: Callable[[Path], FileProbe]
    build_launch_args: Callable[[str, FileProbe, dict[str, Any]], dict[str, Any]]
    component: str = "solve"  # "solve" | "meshing" | "geometry"
    description: str = ""  # surfaced to clients
    # PyFluent settings method to call on load (under session.settings.file.*).
    # Defaults to "read_case" for the Fluent case/mesh family. Data files use
    # "read_data"; Workbench projects use "read_project" (routes to
    # ``session.tui.file.parametric_project.open("<path>")``); etc.
    load_command: str = "read_case"
    # Optional: when set, ``_resolve_load_snippet`` uses this builder
    # to produce the load snippet instead of the default
    # ``session.settings.file.<load_command>(file_name="...")`` form.
    # Used by handlers whose load idiom does not fit that template
    # (e.g. Fluids One geometry CAD import which goes through
    # ``geometry['geometry_1'].file.import_cad(...)``).
    build_load_snippet: Callable[[str, str | None], str] | None = None


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


_REGISTRY: list[FileHandler] = []


def register_handler(handler: FileHandler) -> None:
    """Register a new handler. First match (by longest suffix) wins.

    Registration is idempotent by ``handler.name``. Re-registering a
    handler with the same name replaces the prior entry instead of
    appending a duplicate. This lets an optional consuming layer (one
    that adds non-solve geometry / Prime meshing CAD handlers) import its
    registration module more than once without bloating the registry.

    Boundary note: this OSS package is **solve-only**. It registers
    ONLY Fluent solver file types (case/mesh/data/project/HDF5).
    Geometry (CAD import) and Prime meshing (readcad) handlers are NOT
    registered here. They belong to the geometry/mesh products and are
    registered into this same registry by an optional higher-level layer
    via :func:`register_handler`. A standalone ``ansys-fluent-mcp``
    install therefore exposes a solve-only registry, which is correct
    for the solve leaf's ``compare_files`` tool.

    Parameters
    ----------
    handler : FileHandler
        Callable inspected or registered by the helper.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    _REGISTRY[:] = [h for h in _REGISTRY if h.name != handler.name]
    _REGISTRY.append(handler)
    # Keep the registry sorted so longer suffixes (".cas.h5") match
    # before shorter ones (".h5") regardless of insertion order.
    _REGISTRY.sort(key=lambda h: -max(len(s) for s in h.suffixes))


def list_handlers() -> list[FileHandler]:
    """Return a copy of the current registry (for introspection/tests).

    Returns
    -------
    list[FileHandler]
        Collection containing the operation results.
    """
    return list(_REGISTRY)


def find_handler(path: str | Path) -> FileHandler | None:
    """Return the first registered handler whose suffix matches ``path``.

    Parameters
    ----------
    path : str | Path
        Fluent object path or file-system path to inspect.

    Returns
    -------
    FileHandler | None
        Result produced by the function.
    """
    name = str(path).lower()
    for h in _REGISTRY:
        for suf in h.suffixes:
            if name.endswith(suf.lower()):
                return h
    return None


def find_all_handlers(path: str | Path) -> list[FileHandler]:
    """Return every registered handler whose suffix matches ``path``.

    Used by ``read_file`` to disambiguate suffixes that legitimately
    belong to more than one component. For example, ``.fmd`` is valid as
    both a CAD geometry import (Fluids One Geometry component) and a
    Prime meshing CAD read (Mesh component). The caller resolves the
    ambiguity by inspecting ``handler.component`` against a user-
    supplied ``component`` argument or by prompting the user.

    Parameters
    ----------
    path : str | Path
        Fluent object path or file-system path to inspect.

    Returns
    -------
    list[FileHandler]
        Collection containing the operation results.
    """
    name = str(path).lower()
    out: list[FileHandler] = []
    for h in _REGISTRY:
        if any(name.endswith(s.lower()) for s in h.suffixes):
            out.append(h)
    return out


def supported_suffixes() -> list[str]:
    """Flat, de-duplicated list of every registered suffix.

    Returns
    -------
    list[str]
        Collection containing the operation results.
    """
    out: list[str] = []
    for h in _REGISTRY:
        for s in h.suffixes:
            if s not in out:
                out.append(s)
    return out


# ---------------------------------------------------------------------------
# Built-in: Fluent case / mesh files
# ---------------------------------------------------------------------------


def _probe_fluent_h5(path: Path) -> FileProbe:
    """Read a Fluent ``.cas.h5`` / ``.msh.h5`` archive header.

    The file is opened read-only; we only inspect attributes on
    ``/meshes/<id>`` and the dtype of ``/meshes/<id>/nodes/coords/*``.
    No data is loaded.

    Parameters
    ----------
    path : Path
        Fluent object path or file-system path to inspect.

    Returns
    -------
    FileProbe
        Result produced by the function.
    """
    suf = ".cas.h5" if str(path).lower().endswith(".cas.h5") else ".msh.h5"
    probe = FileProbe(file_type="Fluent case (HDF5)", suffix=suf)

    try:
        import h5py  # type: ignore[import-not-found]
    except ImportError:
        probe.notes.append(
            "h5py not installed — cannot auto-detect dimension/precision. "
            "Install with `pip install h5py` to enable."
        )
        return probe

    try:
        with h5py.File(str(path), "r") as f:
            meshes = f.get("meshes")
            if meshes is None or len(meshes) == 0:
                probe.notes.append("no /meshes group found in HDF5 archive")
                return probe
            # Take the first mesh id (typically "1").
            mesh_id = next(iter(meshes))
            mesh = meshes[mesh_id]
            attrs = dict(mesh.attrs)
            dim = attrs.get("dimension")
            if dim is not None:
                try:
                    probe.dimension = int(dim[0] if hasattr(dim, "__len__") else dim)
                except (TypeError, ValueError, IndexError) as exc:
                    logger.debug("Could not parse mesh dimension: %s", exc)
            lw = attrs.get("lightweight")
            if lw is not None:
                try:
                    probe.is_lightweight = bool(int(lw[0] if hasattr(lw, "__len__") else lw))
                except (TypeError, ValueError, IndexError) as exc:
                    logger.debug("Could not parse lightweight flag: %s", exc)
            # Precision: dtype of node coords. float64 -> double, else single.
            coords = mesh.get("nodes/coords")
            if coords is not None and len(coords) > 0:
                first = next(iter(coords))
                dtype = coords[first].dtype
                probe.precision = "double" if dtype.itemsize >= 8 else "single"
            probe.extra["mesh_id"] = mesh_id
            probe.extra["cell_count"] = (
                int(attrs.get("cellCount", [0])[0]) if "cellCount" in attrs else None
            )
    except Exception as exc:  # boundary, file may be malformed
        probe.notes.append(f"h5py probe failed: {exc}")
    return probe


def _probe_fluent_h5_generic(path: Path) -> FileProbe:
    """Probe a bare ``.h5`` archive to disambiguate case vs data.

    Fluent stores cases and solution data in the same HDF5 container
    format. We peek at the top-level groups:

    * ``/meshes`` present → case (mesh + boundary conditions + setup)
    * ``/results`` present without ``/meshes`` → standalone data file

    The detected load command is stored in ``probe.extra['load_command']``
    so :func:`_resolve_load_snippet` can dispatch correctly. Falls
    back to ``read_case`` when the structure can't be classified.

    Parameters
    ----------
    path : Path
        Fluent object path or file-system path to inspect.

    Returns
    -------
    FileProbe
        Result produced by the function.
    """
    probe = FileProbe(file_type="Fluent archive (HDF5)", suffix=".h5")
    probe.extra["load_command"] = "read_case"  # safe default

    try:
        import h5py  # type: ignore[import-not-found]
    except ImportError:
        probe.notes.append(
            "h5py not installed — cannot disambiguate .h5 archive; "
            "will attempt read_case. Install h5py to enable auto-detect."
        )
        return probe

    try:
        with h5py.File(str(path), "r") as f:
            has_meshes = "meshes" in f
            has_results = "results" in f or "solution" in f
            if has_meshes:
                probe.file_type = "Fluent case (HDF5, bare .h5)"
                probe.extra["load_command"] = "read_case"
                # Reuse the rich case probe to fill in dim/precision.
                rich = _probe_fluent_h5(path)
                probe.dimension = rich.dimension
                probe.precision = rich.precision
                probe.is_lightweight = rich.is_lightweight
                probe.extra.update({k: v for k, v in rich.extra.items() if k != "load_command"})
            elif has_results:
                probe.file_type = "Fluent solution data (HDF5, bare .h5)"
                probe.extra["load_command"] = "read_data"
            else:
                probe.notes.append(
                    "could not classify .h5 archive (no /meshes or /results group); attempting read_case."  # noqa: E501
                )
    except Exception as exc:  # boundary, file may be malformed
        probe.notes.append(f"h5 disambiguation probe failed: {exc}")
    return probe


def _probe_fluent_text(path: Path) -> FileProbe:
    """Probe for legacy text ``.cas`` / ``.msh`` files.

    These are gzip- or text-encoded and don't expose dimension /
    precision via a cheap header scan; the user must answer.

    Parameters
    ----------
    path : Path
        Fluent object path or file-system path to inspect.

    Returns
    -------
    FileProbe
        Result produced by the function.
    """
    suf = ".cas" if str(path).lower().endswith(".cas") else ".msh"
    return FileProbe(
        file_type="Fluent case (legacy text)",
        suffix=suf,
        notes=[
            "legacy .cas/.msh format does not carry inspectable "
            "dimension/precision metadata; defaults will be used "
            "unless the user overrides."
        ],
    )


def _probe_passthrough(path: Path) -> FileProbe:
    """Trivial probe used by formats whose metadata we do not inspect.

    Parameters
    ----------
    path : Path
        Fluent object path or file-system path to inspect.

    Returns
    -------
    FileProbe
        Result produced by the function.
    """
    suf = "".join(path.suffixes).lower() or path.suffix.lower()
    return FileProbe(file_type="binary blob", suffix=suf)


def _build_fluent_launch_args(
    product: str,
    probe: FileProbe,
    choices: dict[str, Any],
) -> dict[str, Any]:
    """Translate (product, probe, user choices) into ``Backend.connect`` kwargs.

    Parameters
    ----------
    product : str
        Fluent product name used when building launch arguments.
    probe : FileProbe
        File probe result used to select launch options.
    choices : dict[str, Any]
        Available choices used to build launch arguments.

    Returns
    -------
    dict[str, Any]
        Mapping containing the operation result.
    """
    args: dict[str, Any] = {}
    if product == "pyfluent":
        # Precision: explicit user choice > probe > default.
        args["precision"] = choices.get("precision") or probe.precision or "double"
        # Dimension is not a launch_fluent kwarg — Fluent infers it
        # from the case file. We keep it in args for traceability.
        if probe.dimension:
            args["dimension"] = probe.dimension
        # Note: lightweight is applied at read_case time
        # (``lightweight_setup=True``), not at launch, because the case
        # is loaded after launch via run_code.
        # ui_mode: "gui" | "headless"; agent runs headless by default.
        ui = choices.get("ui_mode")
        args["ui_mode"] = "gui" if ui == "gui" else "no_gui"
    elif product == "fluids_one":
        # Fluids One has its own session abstraction; surface user
        # choices as instance hints.
        if choices.get("instance_name"):
            args["instance_name"] = choices["instance_name"]
    return args


# Register the two built-in Fluent handlers. Long suffixes go first so
# ".cas.h5" wins over ".h5" if both ever overlap.
register_handler(
    FileHandler(
        name="fluent_case_h5",
        suffixes=(".cas.h5", ".msh.h5"),
        file_type="Fluent case (HDF5)",
        candidate_products=("pyfluent", "fluids_one"),
        needs_mode_choice=True,
        probe=_probe_fluent_h5,
        build_launch_args=_build_fluent_launch_args,
        component="solve",
        description=(
            "Fluent solver case archive (HDF5). Probed for dimension "
            "(2D/3D), precision (single/double) and lightweight flag."
        ),
    )
)
register_handler(
    FileHandler(
        name="fluent_case_text",
        suffixes=(".cas", ".msh", ".cas.gz", ".msh.gz"),
        file_type="Fluent case (legacy text)",
        candidate_products=("pyfluent", "fluids_one"),
        needs_mode_choice=True,
        probe=_probe_fluent_text,
        build_launch_args=_build_fluent_launch_args,
        component="solve",
        description="Legacy text / gzipped Fluent case/mesh; metadata is not inspectable.",
    )
)

# Solution data files (Fluent .dat / .dat.h5 / .dat.gz). Loaded into an
# existing solver session via file.read_data(file_name=...). Requires the
# session to be connected and a case already loaded.
register_handler(
    FileHandler(
        name="fluent_data",
        suffixes=(".dat.h5", ".dat", ".dat.gz"),
        file_type="Fluent solution data",
        candidate_products=("pyfluent", "fluids_one"),
        needs_mode_choice=False,
        probe=_probe_passthrough,
        build_launch_args=_build_fluent_launch_args,
        component="solve",
        description=(
            "Fluent solution data file. Loaded into an existing solver "
            "session via file.read_data; requires a case to be loaded first."
        ),
        load_command="read_data",
    )
)

# Bare ``.h5`` — ambiguous container that can be either a Fluent case
# or a Fluent data file. The probe inspects the HDF5 group structure
# and stores the detected load_command in ``probe.extra``; the
# load_command field below is the literal sentinel ``"auto"`` so
# ``_resolve_load_snippet`` knows to consult the probe.
register_handler(
    FileHandler(
        name="fluent_h5_generic",
        suffixes=(".h5",),
        file_type="Fluent archive (HDF5, auto-detect)",
        candidate_products=("pyfluent", "fluids_one"),
        needs_mode_choice=True,
        probe=_probe_fluent_h5_generic,
        build_launch_args=_build_fluent_launch_args,
        component="solve",
        description=(
            "Bare .h5 archive — Fluent case or data. Auto-detected by peeking at the HDF5 group structure."  # noqa: E501
        ),
        load_command="auto",
    )
)

# Workbench / Fluent project archive. PyFluent v27.1 does not expose
# this on ``session.settings.file``; the canonical path is the TUI
# command ``session.tui.file.parametric_project.open("<path>")``
# (positional file path, no kwargs). ``_resolve_load_snippet`` maps
# the ``read_project`` load_command to that TUI call.
register_handler(
    FileHandler(
        name="fluent_project",
        suffixes=(".flprj", ".cffdb"),
        file_type="Fluent / Workbench project",
        candidate_products=("pyfluent", "fluids_one"),
        needs_mode_choice=False,
        probe=_probe_passthrough,
        build_launch_args=_build_fluent_launch_args,
        component="solve",
        description=(
            "Fluent or Workbench project archive. Loaded via "
            "tui.file.parametric_project.open; lightweight does not "
            "apply."
        ),
        load_command="read_project",
    )
)


# ---------------------------------------------------------------------------
# Non-solve handlers (geometry CAD import, Prime meshing readcad) are
# intentionally NOT registered here. This OSS package is solve-only; an
# optional higher-level layer registers those into this registry via
# :func:`register_handler`. See the boundary note on ``register_handler``.
# ---------------------------------------------------------------------------


__all__ = [
    "FileProbe",
    "FileHandler",
    "register_handler",
    "list_handlers",
    "find_handler",
    "find_all_handlers",
    "supported_suffixes",
    "normalize_path_for_fluent",
]
