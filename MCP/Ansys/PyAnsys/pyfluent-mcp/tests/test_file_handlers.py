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

import sys
from types import SimpleNamespace

from ansys.fluent.mcp.common import file_handlers
from ansys.fluent.mcp.common.file_handlers import (
    FileHandler,
    FileProbe,
    find_all_handlers,
    find_handler,
    list_handlers,
    normalize_path_for_fluent,
    register_handler,
    supported_suffixes,
)


def test_normalize_path_for_fluent_converts_windows_separators():
    """Verify that normalize path for fluent converts windows separators.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    assert normalize_path_for_fluent(r"C:\temp\case.cas.h5") == "C:/temp/case.cas.h5"
    assert normalize_path_for_fluent(r"\\server\share\mesh.msh") == "//server/share/mesh.msh"


def test_find_handler_prefers_longest_suffix():
    """Verify that find handler prefers longest suffix.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    handler = find_handler("elbow.CAS.H5")

    assert handler is not None
    assert handler.name == "fluent_case_h5"


def test_find_all_handlers_and_supported_suffixes_include_builtin_solve_files():
    """Verify that find all handlers and supported suffixes include builtin solve files.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    assert [handler.name for handler in find_all_handlers("mesh.msh.gz")] == ["fluent_case_text"]

    suffixes = supported_suffixes()
    assert ".cas.h5" in suffixes
    assert ".msh.gz" in suffixes
    assert len(suffixes) == len(set(suffixes))


def test_builtin_handler_builds_pyfluent_launch_args_from_probe_and_choices():
    """Verify that builtin handler builds pyfluent launch args from probe and choices.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    handler = find_handler("case.cas.h5")
    assert handler is not None

    args = handler.build_launch_args(
        "pyfluent",
        FileProbe(file_type="Fluent case", suffix=".cas.h5", dimension=2, precision="single"),
        {"ui_mode": "headless"},
    )

    assert args == {"precision": "single", "dimension": 2, "ui_mode": "no_gui"}


def test_list_handlers_returns_copy():
    """Verify that list handlers returns copy.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    handlers = list_handlers()
    handlers.clear()

    assert find_handler("case.cas") is not None


def test_register_handler_replaces_existing_and_finds_all_matches():
    """Verify that register handler replaces existing and finds all matches.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    handler = FileHandler(
        name="custom_overlap",
        suffixes=(".cas.h5", ".custom"),
        file_type="Custom",
        candidate_products=("pyfluent",),
        needs_mode_choice=False,
        probe=lambda path: FileProbe(file_type="Custom", suffix=path.suffix),
        build_launch_args=lambda product, probe, choices: {
            "product": product,
            "suffix": probe.suffix,
            **choices,
        },
        component="solve",
    )
    replacement = FileHandler(
        name="custom_overlap",
        suffixes=(".custom",),
        file_type="Custom Replacement",
        candidate_products=("pyfluent",),
        needs_mode_choice=False,
        probe=lambda path: FileProbe(file_type="Replacement", suffix=path.suffix),
        build_launch_args=lambda _product, _probe, _choices: {"ok": True},
        component="solve",
    )

    register_handler(handler)
    assert find_handler("x.custom").file_type == "Custom"
    register_handler(replacement)
    assert find_handler("x.custom").file_type == "Custom Replacement"
    names = [registered.name for registered in list_handlers()]
    assert names.count("custom_overlap") == 1
    assert [registered.name for registered in find_all_handlers("x.cas.h5")][0] == "fluent_case_h5"


def test_builtin_data_project_and_fluids_one_launch_branches():
    """Verify that builtin data project and fluids one launch branches.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    data = find_handler("solution.dat.h5")
    project = find_handler("workbench.flprj")
    bare = find_handler("archive.h5")

    assert data is not None
    assert data.load_command == "read_data"
    assert project is not None
    assert project.load_command == "read_project"
    assert bare is not None
    assert bare.load_command == "auto"

    args = data.build_launch_args(
        "fluids_one",
        FileProbe(file_type="data", suffix=".dat.h5"),
        {"instance_name": "solver-1"},
    )
    assert args == {"instance_name": "solver-1"}


def test_probe_helpers_handle_missing_h5py_and_passthrough(monkeypatch, tmp_path):
    """Verify that probe helpers handle missing h5py and passthrough.

    Parameters
    ----------
    monkeypatch : Any
        Pytest fixture used to patch environment variables or dependencies.
    tmp_path : Any
        Path for the tmp.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    path = tmp_path / "case.cas.h5"
    path.write_text("not really h5")

    def fake_import(name, *args, **kwargs):
        """Return a fake imported module for the test.

        Parameters
        ----------
        name : Any
            Name of the object, module, or setting being processed.
        args : Any
            Positional arguments forwarded to the callable.
        kwargs : Any
            Keyword arguments forwarded to the callable.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        if name == "h5py":
            raise ImportError("missing")
        return original_import(name, *args, **kwargs)

    original_import = __import__
    monkeypatch.setattr("builtins.__import__", fake_import)

    probe = file_handlers._probe_fluent_h5(path)
    assert probe.suffix == ".cas.h5"
    assert "h5py not installed" in probe.notes[0]

    generic = file_handlers._probe_fluent_h5_generic(tmp_path / "archive.h5")
    assert generic.extra["load_command"] == "read_case"
    assert "cannot disambiguate" in generic.notes[0]

    text_probe = file_handlers._probe_fluent_text(tmp_path / "mesh.msh.gz")
    assert text_probe.suffix == ".msh"
    assert text_probe.notes
    passthrough = file_handlers._probe_passthrough(tmp_path / "solution.dat.h5")
    assert passthrough.suffix == ".dat.h5"


def test_h5_probe_reads_mesh_metadata_and_generic_variants(monkeypatch, tmp_path):
    """Verify that h5 probe reads mesh metadata and generic variants.

    Parameters
    ----------
    monkeypatch : Any
        Pytest fixture used to patch environment variables or dependencies.
    tmp_path : Any
        Path for the tmp.

    Returns
    -------
    None
        The function completes through its side effects.
    """

    class Dataset:
        dtype = SimpleNamespace(itemsize=8)

    class Node(dict):
        def __init__(self, children=None, attrs=None):
            """Initialize the Node instance.

            Parameters
            ----------
            children : Any
                Children to supply to the function.
            attrs : Any
                Attrs to supply to the function.

            Returns
            -------
            None
                The function completes through its side effects.
            """
            super().__init__(children or {})
            self.attrs = attrs or {}

        def get(self, key, default=None):
            """Return a fake mapping or attribute value.

            Parameters
            ----------
            key : Any
                Key used to look up or store the associated value.
            default : Any
                Default value used by the caller when no explicit value is available.

            Returns
            -------
            None
                The function completes through its side effects.
            """
            current = self
            for part in key.split("/"):
                if not isinstance(current, dict) or part not in current:
                    return default
                current = current[part]
            return current

    mesh = Node(
        {"nodes": Node({"coords": Node({"x": Dataset()})})},
        attrs={"dimension": [3], "lightweight": [1], "cellCount": [42]},
    )
    archive = Node({"meshes": Node({"1": mesh})})
    data_archive = Node({"results": Node()})
    unknown_archive = Node({"other": Node()})

    class FakeFile:
        def __init__(self, _path, _mode):
            """Initialize the FakeFile instance.

            Parameters
            ----------
            _path : Any
                Path for the .
            _mode : Any
                Execution or launch mode requested by the caller.

            Returns
            -------
            None
                The function completes through its side effects.
            """
            self.root = archives.pop(0)

        def __enter__(self):
            """Enter the fake context manager.

            Returns
            -------
            None
                The function completes through its side effects.
            """
            return self.root

        def __exit__(self, *_args):
            """Exit the fake context manager.

            Parameters
            ----------
            _args : Any
                Positional arguments forwarded to the wrapped call.

            Returns
            -------
            None
                The function completes through its side effects.
            """
            return False

    monkeypatch.setitem(sys.modules, "h5py", SimpleNamespace(File=FakeFile))
    archives = [archive]
    probe = file_handlers._probe_fluent_h5(tmp_path / "case.cas.h5")
    assert probe.dimension == 3
    assert probe.precision == "double"
    assert probe.is_lightweight is True
    assert probe.extra == {"mesh_id": "1", "cell_count": 42}

    archives = [Node({"meshes": Node()}), data_archive, unknown_archive, RuntimeError("bad")]
    assert file_handlers._probe_fluent_h5(tmp_path / "empty.cas.h5").notes == [
        "no /meshes group found in HDF5 archive"
    ]
    generic_data = file_handlers._probe_fluent_h5_generic(tmp_path / "data.h5")
    assert generic_data.file_type == "Fluent solution data (HDF5, bare .h5)"
    assert generic_data.extra["load_command"] == "read_data"
    generic_unknown = file_handlers._probe_fluent_h5_generic(tmp_path / "unknown.h5")
    assert "could not classify" in generic_unknown.notes[0]

    class RaisingFile:
        def __init__(self, *_args):
            """Initialize the RaisingFile instance.

            Parameters
            ----------
            _args : Any
                Positional arguments forwarded to the wrapped call.

            Returns
            -------
            None
                The function completes through its side effects.
            """
            raise RuntimeError("bad")

    monkeypatch.setitem(sys.modules, "h5py", SimpleNamespace(File=RaisingFile))
    failed = file_handlers._probe_fluent_h5_generic(tmp_path / "bad.h5")
    assert failed.notes == ["h5 disambiguation probe failed: bad"]
