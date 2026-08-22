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

"""Centralized environment-variable configuration for PyFluent MPP.

Every ``FLUIDS_MCP_*`` variable is read once at startup and validated. ``validate_config()``
is called from each leaf's CLI entry point so a typo or out-of-range
value fails fast with a clear message instead of silently corrupting
runtime behavior later.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
import os
from typing import Optional

logger = logging.getLogger("ansys.fluent.mcp.config")


# Public allow-list of recognized environment variables. A startup warning is emitted
# for any ``FLUIDS_MCP_*`` environment variable on the process that is NOT in this set
# so users catch typos like ``FLUIDS_MCP_QRDANT_URL``.
_KNOWN_ENV_VARS: frozenset[str] = frozenset(
    {
        "FLUIDS_MCP_HTTP_TIMEOUT",
        "FLUIDS_MCP_VERIFY_TLS",
        "FLUIDS_MCP_API_OBJECTS_PATH",
        "FLUIDS_MCP_CACHE_DIR",
        "FLUIDS_MCP_CA_BUNDLE",
        "FLUIDS_MCP_LOG_LEVEL",
        "FLUIDS_MCP_SESSION_LOGS",
        "FLUIDS_MCP_DISABLE_SESSION_LOGS",
        "FLUIDS_MCP_SESSION_LOG_DIR",
        "FLUIDS_MCP_SESSION_LOG_LEVEL",
        "FLUIDS_MCP_INTENT_GUARD",
    }
)


@dataclass(frozen=True)
class FluidsMCPConfig:
    """Resolved configuration values."""

    http_timeout: float = 300.0
    verify_tls: bool = True
    api_objects_path: Optional[str] = None
    log_level: str = "INFO"
    warnings: tuple[str, ...] = field(default_factory=tuple)


class ConfigError(ValueError):
    """Raised when an environment variable is set to an invalid value."""


def _parse_bool(name: str, raw: str, *, default: bool) -> bool:
    """Parse a Boolean configuration value from text.

    Parameters
    ----------
    name : str
        Name of the object, module, or setting being processed.
    raw : str
        Raw string value to parse or validate.
    default : bool
        Default value used by the caller when no explicit value is available.

    Returns
    -------
    bool
        Parsed boolean value.
    """
    val = raw.strip().lower()
    if val in {"1", "true", "yes", "on"}:
        return True
    if val in {"0", "false", "no", "off"}:
        return False
    raise ConfigError(
        f"{name}={raw!r} is not a valid boolean (expected one of 1/0/true/false/yes/no/on/off)."
    )


def _parse_float(name: str, raw: str, *, minimum: float = 0.0) -> float:
    """Parse a floating-point configuration value from text.

    Parameters
    ----------
    name : str
        Name of the object, module, or setting being processed.
    raw : str
        Raw string value to parse or validate.
    minimum : float
        Lowest accepted numeric value.

    Returns
    -------
    float
        Parsed floating-point value.
    """
    try:
        v = float(raw)
    except ValueError as exc:
        raise ConfigError(f"{name}={raw!r} is not a valid number.") from exc
    if v <= minimum:
        raise ConfigError(f"{name}={raw!r} must be > {minimum}.")
    return v


def load_config(env: Optional[dict[str, str]] = None) -> FluidsMCPConfig:
    """Read and validate every recognized environment variable.

    Pass ``env`` to inject a synthetic environment for unit tests.
    Unknown ``FLUIDS_MCP_*`` variables produce a warning string in the
    returned config (also logged at WARNING level), but do not abort.

    Parameters
    ----------
    env : Optional[dict[str, str]]
        Environment mapping to read instead of the process environment.

    Returns
    -------
    FluidsMCPConfig
        Result produced by the function.
    """
    src = os.environ if env is None else env
    warnings: list[str] = []

    # Detect typos in ``FLUIDS_MCP_*`` env vars.
    for key in src:
        if key.startswith("FLUIDS_MCP_") and key not in _KNOWN_ENV_VARS:
            msg = f"Unknown environment variable {key!r} (ignored). Known variables: {sorted(_KNOWN_ENV_VARS)}"  # noqa: E501
            warnings.append(msg)
            logger.warning(msg)

    http_timeout = 300.0
    raw = src.get("FLUIDS_MCP_HTTP_TIMEOUT")
    if raw:
        http_timeout = _parse_float("FLUIDS_MCP_HTTP_TIMEOUT", raw, minimum=0.0)

    verify_tls = True
    raw = src.get("FLUIDS_MCP_VERIFY_TLS")
    if raw is not None:
        verify_tls = _parse_bool("FLUIDS_MCP_VERIFY_TLS", raw, default=True)
    if not verify_tls:
        warnings.append(
            "FLUIDS_MCP_VERIFY_TLS is disabled; HTTP backends will not "
            "verify server certificates. Use only on trusted networks."
        )

    log_level = src.get("FLUIDS_MCP_LOG_LEVEL", "INFO").upper()
    if log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        raise ConfigError(
            f"FLUIDS_MCP_LOG_LEVEL={log_level!r} must be one of DEBUG/INFO/WARNING/ERROR/CRITICAL."
        )

    return FluidsMCPConfig(
        http_timeout=http_timeout,
        verify_tls=verify_tls,
        api_objects_path=src.get("FLUIDS_MCP_API_OBJECTS_PATH"),
        log_level=log_level,
        warnings=tuple(warnings),
    )


def validate_config(env: Optional[dict[str, str]] = None) -> FluidsMCPConfig:
    """Validate configuration.

    Alias of :func:`load_config` that raises :class:`ConfigError` on any issue.
    Call once from each CLI entry point.

    Parameters
    ----------
    env : Optional[dict[str, str]]
        Environment mapping to read instead of the process environment.

    Returns
    -------
    FluidsMCPConfig
        Result produced by the function.
    """
    return load_config(env=env)


__all__ = ["FluidsMCPConfig", "ConfigError", "load_config", "validate_config"]
