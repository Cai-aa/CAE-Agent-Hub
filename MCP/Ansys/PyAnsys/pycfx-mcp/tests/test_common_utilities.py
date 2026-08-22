# Copyright (C) 2026 Synopsys, Inc. and ANSYS, Inc. All rights reserved.
# SPDX-License-Identifier: Apache-2.0

"""Coverage-oriented tests for common utility helpers."""

from __future__ import annotations

import time

import pytest

from ansys.cfx.mcp.common.activity_logging import (
    format_iterable_inline,
    sanitize_args,
    summarise_result,
    truncate_text,
)
from ansys.cfx.mcp.common.text_match import (
    edit_distance_le_one,
    fuzzy_normalize,
    sanitize_named_object_key,
)
from ansys.cfx.mcp.common.timings import TimingsCollector, get_collector


@pytest.mark.unit
def test_edit_distance_exact_match() -> None:
    """Verify zero edit-distance strings are accepted."""
    assert edit_distance_le_one("water", "water") is True


@pytest.mark.unit
def test_edit_distance_single_substitution() -> None:
    """Verify one-character substitutions are accepted."""
    assert edit_distance_le_one("water", "waters") is True


@pytest.mark.unit
@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("abc", "xyz"),
        ("pressure", "temperature"),
    ],
)
def test_edit_distance_multiple_changes(left: str, right: str) -> None:
    """Verify strings requiring multiple edits are rejected."""
    assert edit_distance_le_one(left, right) is False


@pytest.mark.unit
def test_fuzzy_normalize_returns_unique_match() -> None:
    """Verify fuzzy matching normalizes to a unique candidate."""
    allowed = ["water-vapor", "nitrogen"]
    assert fuzzy_normalize("water-vapour", allowed) == "water-vapor"


@pytest.mark.unit
def test_fuzzy_normalize_rejects_ambiguous_match() -> None:
    """Verify ambiguous fuzzy matches return ``None``."""
    allowed = ["cat", "cut"]
    assert fuzzy_normalize("cot", allowed) is None


@pytest.mark.unit
def test_fuzzy_normalize_rejects_non_string_values() -> None:
    """Verify non-string fuzzy inputs are ignored."""
    assert fuzzy_normalize(123, ["abc"]) is None


@pytest.mark.unit
def test_sanitize_named_object_key_rewrites_whitespace() -> None:
    """Verify whitespace is normalized to NamedObject-safe separators."""
    sanitized, notice = sanitize_named_object_key("oil inlet")

    assert sanitized == "oil-inlet"
    assert notice is not None
    assert "auto-corrected" in notice


@pytest.mark.unit
def test_sanitize_named_object_key_passthrough() -> None:
    """Verify already-clean names are returned unchanged."""
    sanitized, notice = sanitize_named_object_key("pressure-outlet-1")

    assert sanitized == "pressure-outlet-1"
    assert notice is None


@pytest.mark.unit
def test_sanitize_named_object_key_non_string_passthrough() -> None:
    """Verify non-string names are returned unchanged."""
    sanitized, notice = sanitize_named_object_key(42)  # type: ignore[arg-type]

    assert sanitized == 42
    assert notice is None


@pytest.mark.unit
def test_timings_collector_records_and_summarizes() -> None:
    """Verify timing metrics are recorded and summarized."""
    collector = TimingsCollector()

    collector.record("tool", "run", 10.0)
    collector.record("tool", "run", 30.0, errored=True)

    snapshot = collector.snapshot()
    summary = collector.summary()

    assert snapshot["tool"][0]["count"] == 2
    assert snapshot["tool"][0]["errors"] == 1
    assert summary["tool"]["count"] == 2
    assert summary["tool"]["errors"] == 1
    assert summary["tool"]["avg_ms"] == 20.0


@pytest.mark.unit
def test_timings_context_manager_records_exceptions() -> None:
    """Verify timing context manager records failures."""
    collector = TimingsCollector()

    with pytest.raises(RuntimeError):
        with collector.time("backend", "solve"):
            raise RuntimeError("boom")

    snapshot = collector.snapshot()
    assert snapshot["backend"][0]["errors"] == 1


@pytest.mark.unit
def test_timings_reset_and_uptime() -> None:
    """Verify collector reset clears accumulated state."""
    collector = TimingsCollector()
    collector.record("tool", "one", 1.0)

    time.sleep(0.01)
    assert collector.uptime_s() >= 0.0

    collector.reset()

    assert collector.snapshot() == {}


@pytest.mark.unit
def test_timings_collector_overflow_bucket() -> None:
    """Verify overflow tracking activates when scope tables are full."""
    collector = TimingsCollector()

    table = {str(i): object() for i in range(1024)}
    collector._scopes["tool"] = table  # type: ignore[assignment]

    collector.record("tool", "new-key", 3.0)

    assert "__overflow__" in collector._scopes["tool"]


@pytest.mark.unit
def test_get_collector_shares_state_between_calls() -> None:
    """Verify the module collector preserves shared timing state."""
    collector = get_collector()
    collector.reset()

    collector.record("tool", "run", 5.0)

    second = get_collector()
    snapshot = second.snapshot()

    assert snapshot["tool"][0]["count"] == 1
    assert snapshot["tool"][0]["total_ms"] == 5.0

    collector.reset()


@pytest.mark.unit
def test_sanitize_args_redacts_and_truncates() -> None:
    """Verify logging argument sanitization rules."""
    payload = {
        "api_key": "secret-token",
        "description": "x" * 1200,
        "nested": ["short", {"password": "hidden"}],
    }

    sanitized = sanitize_args(payload)

    assert sanitized["api_key"] == "<redacted len=12>"
    assert "chars" in sanitized["description"]
    assert sanitized["nested"][1]["password"] == "<redacted len=6>"


@pytest.mark.unit
def test_sanitize_args_handles_non_string_secret_values() -> None:
    """Verify non-string secrets use generic redaction markers."""
    sanitized = sanitize_args({"token": {"secret": True}})

    assert sanitized["token"] == "<redacted>"


@pytest.mark.unit
def test_sanitize_args_preserves_keep_full_keys() -> None:
    """Verify special keys bypass truncation."""
    long_value = "x" * 2000

    sanitized = sanitize_args({"path": long_value})

    assert sanitized["path"] == long_value


@pytest.mark.unit
def test_summarise_result_handles_large_collections() -> None:
    """Verify large mappings and lists are compacted."""
    result = {
        "items": list(range(20)),
        "mapping": {f"k{i}": i for i in range(20)},
    }

    summary = summarise_result(result)

    assert summary["items"]["_kind"] == "list"
    assert summary["items"]["_size"] == 20
    assert summary["mapping"]["_kind"] == "dict"
    assert summary["mapping"]["_size"] == 20


@pytest.mark.unit
def test_summarise_result_non_mapping() -> None:
    """Verify non-mapping results are truncated directly."""
    result = summarise_result("x" * 3000, limit=100)

    assert isinstance(result, str)
    assert "chars" in result


@pytest.mark.unit
def test_summarise_value_handles_small_collections() -> None:
    """Verify small collections remain expanded."""
    result = summarise_result({"items": [1, 2, 3], "mapping": {"a": 1}})

    assert result["items"] == [1, 2, 3]
    assert result["mapping"] == {"a": 1}


@pytest.mark.unit
def test_format_iterable_inline_truncates_output() -> None:
    """Verify iterable formatting respects length limits."""
    text = format_iterable_inline(["alpha", "beta", "gamma", "delta"], limit=12)

    assert text == "alpha, …"
    assert text.endswith("…")


@pytest.mark.unit
def test_format_iterable_inline_without_truncation() -> None:
    """Verify iterable formatting preserves short inputs."""
    text = format_iterable_inline(["alpha", "beta"], limit=100)

    assert text == "alpha, beta"


@pytest.mark.unit
def test_truncate_text_handles_empty_and_long_values() -> None:
    """Verify text truncation behavior."""
    assert truncate_text("") == ""

    long_text = truncate_text("a" * 5000, limit=100)
    assert long_text.endswith("chars>")
