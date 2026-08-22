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

"""Runtime configuration for the PyLumerical MCP server.

Reads environment variables (loaded by ``python-dotenv`` from ``.env`` when
present) and exposes a single immutable ``Config`` object the server consults
at startup.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Optional

from dotenv import load_dotenv


def _envbool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() not in {"0", "false", "no", "off", ""}


@dataclass(frozen=True)
class Config:
    """Resolved configuration for one server process."""

    hide_gui: bool = False
    license_file: Optional[str] = None
    install_dir: Optional[str] = None


def load_config() -> Config:
    """Load environment variables (via ``.env`` if present) and build a ``Config`` object."""
    load_dotenv()
    return Config(
        hide_gui=_envbool("LUMERICAL_HIDE_GUI", default=False),
        license_file=os.environ.get("ANSYSLMD_LICENSE_FILE"),
        install_dir=os.environ.get("LUMERICAL_INSTALL_DIR"),
    )


__all__ = ["Config", "load_config"]
