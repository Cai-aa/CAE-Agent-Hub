from __future__ import annotations

import json
from pathlib import Path

import pytest

from ansa_mcp_bridge.config import load_config


def _write_config(path: Path, allowed_roots) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "host": "127.0.0.1",
                "port": 48762,
                "token": "a" * 64,
                "allowed_roots": allowed_roots,
                "request_timeout_seconds": 120,
            }
        ),
        encoding="utf-8",
    )
    return path


def test_load_config_accepts_and_creates_absolute_allowed_roots(
    tmp_path: Path,
) -> None:
    root = tmp_path / "workspace"
    config_path = _write_config(tmp_path / "config" / "bridge.json", [str(root)])

    loaded_path, config = load_config(config_path)

    assert loaded_path == config_path.resolve()
    assert config["allowed_roots"] == [str(root.resolve())]
    assert root.is_dir()


@pytest.mark.parametrize(
    ("allowed_roots", "message"),
    [
        ([], "allowed_roots must be a non-empty list"),
        ([""], r"allowed_roots\[0\] must be a non-empty string"),
        (["   "], r"allowed_roots\[0\] must be a non-empty string"),
        (["relative/path"], r"allowed_roots\[0\] must be an absolute path"),
        ([123], r"allowed_roots\[0\] must be a non-empty string"),
    ],
)
def test_load_config_rejects_invalid_allowed_root_lists(
    tmp_path: Path, allowed_roots, message: str
) -> None:
    config_path = _write_config(tmp_path / "bridge.json", allowed_roots)

    with pytest.raises(ValueError, match=message):
        load_config(config_path)


def test_load_config_rejects_a_single_path_string_without_creating_fragments(
    tmp_path: Path,
) -> None:
    root = tmp_path / "must-not-exist"
    config_path = _write_config(tmp_path / "config" / "bridge.json", str(root))

    with pytest.raises(ValueError, match="allowed_roots must be a non-empty list"):
        load_config(config_path)

    assert not root.exists()


def test_load_config_validates_every_root_before_creating_any_directory(
    tmp_path: Path,
) -> None:
    root = tmp_path / "must-not-be-created"
    config_path = _write_config(
        tmp_path / "config" / "bridge.json",
        [str(root), "relative/path"],
    )

    with pytest.raises(
        ValueError, match=r"allowed_roots\[1\] must be an absolute path"
    ):
        load_config(config_path)

    assert not root.exists()
