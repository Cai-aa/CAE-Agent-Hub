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

"""Utilities for resolving network-related environment configuration."""

from __future__ import annotations

import os


def env_flag(name: str, *, default: bool = False) -> bool:
    """Return a normalized boolean environment flag."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    return value in {"1", "true", "yes", "on"}


def resolve_tls_verify(env: dict[str, str] | None = None) -> bool | str:
    """Resolve TLS verification configuration from environment."""
    src = env or os.environ
    if src.get("FLUIDS_MCP_CA_BUNDLE"):
        return src["FLUIDS_MCP_CA_BUNDLE"]
    if src.get("SSL_CERT_FILE"):
        return src["SSL_CERT_FILE"]
    if src.get("REQUESTS_CA_BUNDLE"):
        return src["REQUESTS_CA_BUNDLE"]
    verify_tls = (src.get("FLUIDS_MCP_VERIFY_TLS") or "true").strip().lower()
    return verify_tls not in {"0", "false", "off", "no"}
