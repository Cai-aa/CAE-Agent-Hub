from __future__ import annotations

from pathlib import Path

import pytest

from ansa_mcp.settings import safe_relative_path, within


def test_safe_relative_path_adds_required_suffix() -> None:
    assert safe_relative_path("runs/model", suffix=".ansa") == Path(
        "runs/model.ansa"
    )
    assert safe_relative_path("runs/model.ANSA", suffix=".ansa") == Path(
        "runs/model.ANSA"
    )


@pytest.mark.parametrize(
    "value",
    [
        "../escape.ansa",
        "nested/../../escape.ansa",
        "C:/escape.ansa",
        "bad:name.ansa",
        "bad?.ansa",
    ],
)
def test_safe_relative_path_rejects_unsafe_values(value: str) -> None:
    with pytest.raises(ValueError):
        safe_relative_path(value, suffix=".ansa")


def test_within_accepts_descendant_and_rejects_sibling(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    inside = root / "job" / "model.ansa"
    assert within(inside, root) == inside.resolve()

    with pytest.raises(ValueError, match="outside the allowed workspace"):
        within(tmp_path / "workspace-sibling" / "model.ansa", root)

