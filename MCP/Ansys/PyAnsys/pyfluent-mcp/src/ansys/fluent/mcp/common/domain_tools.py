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

"""Domain-tool registration framework.

A *domain tool* is one that does pure backend/catalog/Fluent
introspection work with no dependency on a plan builder, journal,
learned constraints, or recipe registry. Every domain tool lives on an
MCP leaf. When an optional higher-level agent layer is installed, it
reaches these tools over the MCP wire (an MCP client pool), not by
direct Python import. This package never imports that agent layer. The
dependency direction is strictly one-way (agent → this package).

The contract is intentionally small so that migrating a handler from
the agent layer is a mechanical rewrite. A domain tool is a
**typed** async function with the signature::

    async def my_tool_impl(
        backend: Backend,
        *,
        arg1: int,
        arg2: str | None = None,
    ) -> dict[str, Any]: ...

It is paired with a name, description, and (optional) live-session flag::

    DomainTool(
        spec=DomainToolSpec(name="my_tool", description="..."),
        handler=my_tool_impl,
    )

The leaf calls :func:`FluidsLeafMCP._register_domain_tools` with a
list of these. The helper synthesizes a wrapper whose
``inspect.Signature`` mirrors the handler minus the ``backend``
parameter so FastMCP can extract the JSON input schema from the
wrapper. There is no parallel JSON-schema-on-the-spec to keep in
sync with the handler signature.

The handler receives the leaf's active
:class:`ansys.fluent.mcp.common.backend.Backend` plus the validated
keyword arguments. There is no loop state, no journal, no plan
builder. A tool that needs the plan builder, journal, or recipe
registry is **agent-only** by definition and lives in the optional
agent layer instead, not in this package.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

# ``Backend`` is only referenced in docstrings / type comments below
# (handlers take it as their first positional argument). We avoid a
# real import here so this module stays usable in environments where
# ``ansys.fluent.mcp.common.backend`` is intentionally not on the path
# (e.g. the FluidsOne tenant-only deployment that ships the descriptor
# dataclasses without the full backend stack). When a handler needs
# the type annotation it imports ``Backend`` directly.

#: Handler signature for a domain tool. The first positional argument
#: is the leaf's active backend (a :class:`ansys.fluent.mcp.common.backend.Backend`);
#: every subsequent argument must be keyword-only with an explicit
#: type annotation so FastMCP can synthesize the input JSON schema
#: from the function signature. Returning ``dict[str, Any]`` is
#: conventional but the framework accepts any JSON-serializable
#: payload (list, scalar, …).
DomainToolHandler = Callable[..., Awaitable[Any]]


@dataclass(frozen=True)
class DomainToolSpec:
    """Metadata describing a domain tool to a MCP leaf.

    The ``parameters`` field is **optional**. When omitted, the
    framework derives the JSON schema from the handler's typed
    signature. (See :func:`schema_from_signature`). Setting an explicit
    JSON schema is only useful when the handler accepts a union/variant
    payload that can't be expressed cleanly with Python type
    hints.

    Note (architecture boundary): This package never builds an
    agent-side spec object. That would require importing the optional
    higher-level agent layer, which is forbidden. (Dependency direction
    is agent → this package, never the reverse). The agent layer, when
    installed, constructs its own spec from this descriptor plus
    :func:`schema_from_signature`.
    """

    name: str
    description: str
    parameters: dict[str, Any] | None = field(default=None)


@dataclass(frozen=True)
class DomainTool:
    """A registered domain tool — spec plus typed async handler.

    Instances of this dataclass live in each leaf's
    ``products/<leaf>/lib/domain_tools.py`` module and are passed
    to :meth:`FluidsLeafMCP._register_domain_tools` during the
    leaf's ``_register_tools()`` override.
    """

    spec: DomainToolSpec
    handler: DomainToolHandler
    #: When true, the leaf wraps the handler with a connectivity
    #: check that returns a structured error if no backend is
    #: connected. Defaults to False because most domain tools that
    #: do not need a session are pure catalog / reference queries.
    requires_live_session: bool = False


def schema_from_signature(handler: DomainToolHandler) -> dict[str, Any]:
    """Derive a minimal JSON schema from a typed handler signature.

    Drops the leading ``backend`` parameter and emits one
    ``properties`` entry per keyword-only argument. The mapping is
    intentionally small: ``str -> "string"``, ``int -> "integer"``,
    ``float -> "number"``, ``bool -> "boolean"``, ``dict -> "object"``,
    ``list -> "array"`` plus ``None`` for ``Optional[...]`` arms.
    Anything else falls back to a parameter without a ``type``
    constraint. The handler is still callable. The schema just
    documents fewer expectations.

    Parameters
    ----------
    handler : DomainToolHandler
        Callable inspected or registered by the helper.

    Returns
    -------
    dict[str, Any]
        Mapping containing the operation result.
    """
    import inspect
    import types
    import typing

    sig = inspect.signature(handler)
    params = list(sig.parameters.values())[1:]  # drop ``backend``
    type_map: dict[Any, str] = {
        str: "string",
        int: "integer",
        float: "number",
        bool: "boolean",
        dict: "object",
        list: "array",
    }
    properties: dict[str, Any] = {}
    required: list[str] = []
    for p in params:
        prop: dict[str, Any] = {}
        ann = p.annotation
        origin = typing.get_origin(ann)
        # Unwrap both ``typing.Optional``/``typing.Union`` and the PEP 604
        # ``X | None`` form (``types.UnionType``). The latter's origin
        # differs across Python versions (notably 3.14), so match it by
        # type rather than relying on a stable ``repr``.
        if (
            origin is typing.Union
            or origin is getattr(types, "UnionType", ())
            or repr(origin) == "typing.Union"
        ):
            args = [a for a in typing.get_args(ann) if a is not type(None)]
            ann = args[0] if args else ann
        json_type = type_map.get(ann)
        if json_type is not None:
            prop["type"] = json_type
        properties[p.name] = prop
        if p.default is inspect.Parameter.empty:
            required.append(p.name)
    schema: dict[str, Any] = {
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
    }
    if required:
        schema["required"] = required
    return schema


__all__ = [
    "DomainTool",
    "DomainToolHandler",
    "DomainToolSpec",
    "schema_from_signature",
]
