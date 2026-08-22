# Copyright (C) 2025 - 2026 ANSYS, Inc. and/or its affiliates.
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

"""Common context definitions for PyAnsys MCP servers.

This module provides base context classes that can be extended by
product-specific MCP implementations.
"""

from dataclasses import dataclass, field
from typing import Any, Optional

__all__ = ["PyAnsysBaseAppContext"]


@dataclass
class PyAnsysBaseAppContext:
    """Base application context for PyAnsys MCP servers.

    This class provides a common structure that product-specific contexts
    can extend. The ``product_instance`` field can hold any Ansys product
    connection (such as MAPDL, Fluent, or Maxwell).

    Attributes
    ----------
    product_instance : [Any], default: None
        Main product instance (such as MAPDL or Fluent) associated with the context.
    python_executable : [Any], default: None
        Python executable to use for the session.
    python_session : [Any], default: None
        Instance of the ``PersistentPythonSession`` class for managing the persistent
        Python session.
    metadata : dict
        Dictionary for storing arbitrary metadata related to the context.
    command_history : list
        List to keep track of executed commands in the session.

    Examples
    --------
    Extend the base context for a specific product:

    >>> from ansys.common.mcp import PyAnsysBaseAppContext
    >>> from dataclasses import dataclass
    >>> from typing import Optional, Any
    >>>
    >>> @dataclass
    >>> class NewAppContext(PyAnsysBaseAppContext):
    ...     instance: Optional[Any] = None
    ...
    ...     @property
    ...     def product_instance(self):
    ...         return self.instance

    """

    product_instance: Optional[Any] = None
    python_executable: Optional[Any] = None
    python_session: Optional[Any] = None  # PersistentPythonSession instance
    metadata: dict[str, Any] = field(default_factory=dict)
    command_history: list[str] = field(default_factory=list)
