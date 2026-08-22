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


from pathlib import Path

import pytest

from ansys.fluent.mcp.solve.catalog import help as catalog_help


def test_extract_deduplicates_docstrings_by_python_name():
    """Verify that extract deduplicates docstrings by python name.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    text = '''
class temperature:
    """Static temperature value."""
    _python_name = "t"

class alternate_temperature:
    """Inlet temperature value."""
    _python_name = "t"

class duplicate_temperature:
    """Static temperature value."""
    _python_name = "t"

class velocity:
    """Velocity magnitude."""
    fluent_name = "velocity"
'''

    result = catalog_help._extract(text)

    assert result["t"] == "Static temperature value.\n\nInlet temperature value."
    assert result["velocity"] == "Velocity magnitude."


def test_build_help_map_reads_and_uses_cache(monkeypatch, tmp_path):
    """Verify that build help map reads and uses cache.

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
    monkeypatch.setenv("FLUIDS_MCP_CACHE_DIR", str(tmp_path / "cache"))
    settings_file = tmp_path / "settings_271.py"
    settings_file.write_text(
        'class pressure:\n    """Operating pressure."""\n    _python_name = "pressure"\n',
        encoding="utf-8",
    )

    first = catalog_help.build_help_map(settings_path=settings_file)
    monkeypatch.setattr(
        catalog_help,
        "_extract",
        lambda text: (_ for _ in ()).throw(AssertionError("cache should be used")),
    )
    second = catalog_help.build_help_map(settings_path=settings_file)

    assert first == {"pressure": "Operating pressure."}
    assert second == first
    assert list((tmp_path / "cache").glob("api_help_*.json"))


def test_build_help_map_handles_missing_and_bad_inputs(monkeypatch, tmp_path):
    """Verify that build help map handles missing and bad inputs.

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
    monkeypatch.setenv("FLUIDS_MCP_CACHE_DIR", str(tmp_path / "cache"))

    def missing_settings_file():
        raise FileNotFoundError("missing mandatory settings catalog")

    monkeypatch.setattr(catalog_help, "_resolve_settings_file", missing_settings_file)

    with pytest.raises(FileNotFoundError, match="mandatory settings catalog"):
        catalog_help.build_help_map(settings_path=None, use_cache=False)
    assert catalog_help.build_help_map(settings_path=tmp_path / "missing.py", use_cache=False) == {}

    directory = tmp_path / "settings_dir.py"
    directory.mkdir()
    assert catalog_help.build_help_map(settings_path=directory, use_cache=False) == {}


def test_resolve_settings_file_and_default_cache(monkeypatch, tmp_path):
    """Verify that resolve settings file and default cache.

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
    package_dir = tmp_path / "ansys" / "fluent" / "core"
    generated = package_dir / "generated" / "solver"
    generated.mkdir(parents=True)
    older = generated / "settings_270.py"
    newer = generated / "settings_271.py"
    older.write_text("", encoding="utf-8")
    newer.write_text("", encoding="utf-8")

    class FakePackagePath:
        def __init__(self, dist_path, target):
            self._dist_path = dist_path
            self._target = target
            self.parts = dist_path.parts

        def __str__(self):
            return self._dist_path.as_posix()

        def locate(self):
            return self._target

    fake_files = [
        FakePackagePath(Path("ansys/fluent/core/generated/solver/settings_270.py"), older),
        FakePackagePath(Path("ansys/fluent/core/generated/solver/settings_271.py"), newer),
        FakePackagePath(
            Path("ansys/fluent/core/generated/meshing/settings_999.py"),
            tmp_path / "ignored.py",
        ),
    ]
    monkeypatch.setattr(catalog_help.metadata, "files", lambda name: fake_files)

    assert catalog_help._resolve_settings_file() == newer

    calls = []

    def fake_build_help_map():
        """Build a fake help map for catalog tests.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        calls.append("called")
        return {"leaf": "doc"}

    catalog_help.reset_default_help_map()
    monkeypatch.setattr(catalog_help, "build_help_map", fake_build_help_map)
    assert catalog_help.get_default_help_map() == {"leaf": "doc"}
    assert catalog_help.get_default_help_map() == {"leaf": "doc"}
    assert calls == ["called"]
    catalog_help.reset_default_help_map()
