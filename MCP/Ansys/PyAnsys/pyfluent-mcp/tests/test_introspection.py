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

from types import SimpleNamespace

from ansys.fluent.mcp.solve.backends import introspection


class FakeNode:
    def __init__(
        self,
        *,
        state=None,
        active=True,
        child_names=None,
        names=None,
        allowed=None,
        attrs=None,
    ):
        """Initialize the FakeNode instance.

        Parameters
        ----------
        state : Any
            State to supply to the function.
        active : Any
            Active to supply to the function.
        child_names : Any
            Child names to supply to the function.
        names : Any
            Object names supplied to the helper.
        allowed : Any
            Allowed to supply to the function.
        attrs : Any
            Attrs to supply to the function.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        self._state = state
        self._active = active
        self.child_names = list(child_names) if child_names else []
        self._names = names
        self._allowed = allowed
        self._items = {}
        self._attrs = attrs or {}

    def __getattribute__(self, name):
        """Return a controlled attribute value for the test object.

        Parameters
        ----------
        name : Any
            Name of the object, module, or setting being processed.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        if name in {"__getitem__", "keys", "get_object_names"}:
            names = object.__getattribute__(self, "_names")
            if names is None:
                raise AttributeError(name)
        return object.__getattribute__(self, name)

    def add(self, name, node):
        """Add the value needed by the operation.

        Parameters
        ----------
        name : Any
            Name of the object, module, or setting being processed.
        node : Any
            Node being inspected or registered.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        setattr(self, name, node)
        self._items[name] = node
        if name not in self.child_names:
            self.child_names.append(name)
        return node

    def __getitem__(self, key):
        """Return a controlled item value for the test object.

        Parameters
        ----------
        key : Any
            Key used to look up or store the associated value.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        if self._names is None:
            raise KeyError(key)
        return self._items[key]

    def keys(self):
        """Return the configured mapping keys.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        if self._names is None:
            raise RuntimeError("not a collection")
        return self._items.keys()

    def get_object_names(self):
        """Return the object names.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        if self._names is None:
            raise RuntimeError("not a collection")
        return list(self._names)

    def get_state(self):
        """Return the state.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        if isinstance(self._state, BaseException):
            raise self._state
        return self._state

    def is_active(self):
        """Return whether active.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        if isinstance(self._active, BaseException):
            raise self._active
        return self._active

    def allowed_values(self):
        """Return allowed values for the fake setting.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        if self._allowed is None:
            return []
        return list(self._allowed)

    def get_active_child_names(self):
        """Return the active child names.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        return list(self._attrs.get("active_children", []))


class Scheme:
    def __init__(self, *responses):
        """Initialize the Scheme instance.

        Parameters
        ----------
        responses : Any
            Responses to supply to the function.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        self.responses = list(responses)
        self.calls = []

    def eval(self, expr):
        """Evaluate the fake expression for the test.

        Parameters
        ----------
        expr : Any
            Expr to supply to the function.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        self.calls.append(expr)
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


class CallableNode(FakeNode):
    def __call__(self):
        """Invoke the fake callable for the test.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        return "called"


class BrokenChildNode(FakeNode):
    def __getattribute__(self, name):
        """Return a controlled attribute value for the test object.

        Parameters
        ----------
        name : Any
            Name of the object, module, or setting being processed.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        if name == "broken_child":
            raise RuntimeError("child unavailable")
        return super().__getattribute__(name)


def test_path_normalisation_and_resolution_support_indexed_keys():
    """Verify that path normalisation and resolution support indexed keys.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    assert introspection._split_outside_brackets("a.b[c.d]/e", "/.") == ["a", "b[c.d]", "e"]
    assert introspection.normalise_attr_path(
        "settings/setup/boundary-conditions/wall[hot-wall]"
    ) == [
        "setup",
        "boundary_conditions",
        "wall[hot-wall]",
    ]

    root = FakeNode()
    setup = root.add("setup", FakeNode())
    bcs = setup.add("boundary_conditions", FakeNode())
    wall = bcs.add("wall", FakeNode(names=["hot-wall"]))
    hot_wall = wall.add("hot-wall", FakeNode(state={"thermal": "ok"}))
    phase_container = hot_wall.add("phase", FakeNode(names=["phase-1"]))
    phase = phase_container.add("phase-1", FakeNode(state={"momentum": True}))

    assert introspection.resolve_path(root, "setup/boundary-conditions/wall[hot-wall]") is hot_wall
    assert introspection.resolve_path(hot_wall, "phase.phase_1") is phase


def test_discover_named_objects_via_scheme_handles_dict_list_and_fallback():
    """Verify that discover named objects via scheme handles dict list and fallback.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    assert introspection.discover_named_objects_via_scheme(SimpleNamespace()) is None

    solver = SimpleNamespace(scheme=Scheme({"setup/wall": ["w1", 2]}))
    assert introspection.discover_named_objects_via_scheme(solver) == {"setup/wall": ["w1", "2"]}

    fallback_solver = SimpleNamespace(
        scheme=Scheme(RuntimeError("no silence"), [("setup/inlet", "in")])
    )
    assert introspection.discover_named_objects_via_scheme(fallback_solver) == {
        "setup/inlet": ["in"]
    }

    bad_solver = SimpleNamespace(scheme=Scheme(object()))
    assert introspection.discover_named_objects_via_scheme(bad_solver) is None

    class CallableScheme:
        def __call__(self, expr):
            """Invoke the fake callable for the test.

            Parameters
            ----------
            expr : Any
                Expr to supply to the function.

            Returns
            -------
            None
                The function completes through its side effects.
            """
            self.expr = expr
            return (("setup/outlet", "out-1", "out-2"),)

    callable_scheme = CallableScheme()
    assert introspection.discover_named_objects_via_scheme(
        SimpleNamespace(scheme=callable_scheme)
    ) == {"setup/outlet": ["out-1", "out-2"]}
    assert "api-get-named-object-names" in callable_scheme.expr


def test_discover_named_objects_via_walk_finds_collections_and_respects_caps():
    """Verify that discover named objects via walk finds collections and respects caps.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    root = FakeNode()
    setup = root.add("setup", FakeNode())
    bcs = setup.add("boundary_conditions", FakeNode())
    bcs.add("wall", FakeNode(names=["w1", "w2"]))
    bcs.add("velocity_inlet", FakeNode(names=[]))

    assert introspection.discover_named_objects_via_walk(root) == {
        "setup/boundary-conditions/wall": ["w1", "w2"],
        "setup/boundary-conditions/velocity-inlet": [],
    }
    assert introspection.discover_named_objects_via_walk(root, max_depth=1) == {}

    broken_root = BrokenChildNode(child_names=["broken_child", "ok"])
    broken_root.add("ok", FakeNode(names=["kept"]))
    assert introspection.discover_named_objects_via_walk(broken_root) == {"ok": ["kept"]}
    assert introspection.discover_named_objects_via_walk(root, max_entries=1) == {
        "setup/boundary-conditions/wall": ["w1", "w2"]
    }


def test_collect_global_state_skips_inactive_commands_and_bounds_large_values():
    """Verify that collect global state skips inactive commands and bounds large values.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    root = FakeNode()
    setup = root.add("setup", FakeNode())
    models = setup.add("models", FakeNode())
    models.add(
        "energy",
        FakeNode(state={"enabled": True}, active=True, attrs={"active_children": ["enabled"]}),
    )
    models.add("viscous", FakeNode(active=False))
    setup.add("exploding", FakeNode(active=RuntimeError("inactive object")))
    command = setup.add("initialize", CallableNode())
    command.argument_names = ("method",)
    method = command.add("method", FakeNode(state="should not read"))
    method._parent = command
    method._python_name = "method"

    state = introspection.collect_global_state(
        root,
        [
            "setup.models.energy",
            "setup.models.viscous",
            "setup.initialize",
            "setup.initialize.method",
            "setup.exploding",
            "missing",
        ],
    )

    assert state["setup.models.energy"] == {"enabled": True}
    assert state["setup.models.viscous"] == {"inactive": True}
    assert state["setup.initialize"] == {"skipped": "command_or_query"}
    assert state["setup.initialize.method"] == {"skipped": "command_argument"}
    assert state["setup.exploding"] == {"inactive": True}
    assert state["missing"]["error"]

    assert introspection._bound_state({"x": "y" * 100}, 10) == "<large_state_omitted>"
    assert introspection._bound_state(object(), 10).startswith("<")
    assert introspection._prune_inactive_children(
        FakeNode(attrs={"active_children": ["a"]}), {"a": 1, "b": 2}
    ) == {"a": 1}
    assert introspection._prune_inactive_children(
        FakeNode(attrs={"active_children": ["c"]}), {"a": 1}
    ) == {"a": 1}


def test_collect_targeted_context_collects_state_names_allowed_values_and_instances():
    """Verify that collect targeted context collects state names allowed values and instances.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    root = FakeNode()
    setup = root.add("setup", FakeNode())
    models = setup.add("models", FakeNode())
    models.add("multiphase", FakeNode(state={"model": "vof"}))
    bcs = setup.add("boundary_conditions", FakeNode())
    inlet = bcs.add("velocity_inlet", FakeNode(names=["inlet-1"]))
    inlet_instance = inlet.add("inlet-1", FakeNode(child_names=["phase"], state={"ok": True}))
    phase = inlet_instance.add("phase", FakeNode())
    phase.add("phase-1", FakeNode(child_names=["momentum", "thermal"]))
    phase.add("mixture", FakeNode(child_names=["momentum"]))

    leaf = setup.add("leaf", FakeNode(state={"value": 1}))
    leaf.add("mode", FakeNode(allowed=["a", "b"]))
    phases = models.add("multiphase_phases", FakeNode(names=["phase-1"]))
    phases.add("phase-1", FakeNode(state={"phase": True}))

    result = introspection.collect_targeted_context(
        root,
        paths_to_check=["setup.leaf", "setup.missing"],
        named_object_types=[
            "setup.boundary_conditions.velocity_inlet",
            "setup.models.multiphase_phases",
        ],
        instance_state_fetch=["setup.boundary_conditions.velocity_inlet/inlet-1"],
    )

    assert result["active_status"]["setup.leaf"] is True
    assert result["active_status"]["setup.missing"] is False
    assert result["state_values"]["setup.leaf"] == {"value": 1}
    assert result["child_names"]["setup.leaf"] == ["mode"]
    assert result["named_objects"]["setup.boundary_conditions.velocity_inlet"] == ["inlet-1"]
    assert result["allowed_values"]["setup.leaf.mode"] == ["a", "b"]
    assert result["state_values"]["setup.boundary_conditions.velocity_inlet/inlet-1"] == {
        "ok": True
    }


def test_collect_targeted_context_handles_collection_fallbacks_and_inactive_instances():
    """Verify that collect targeted context handles collection fallbacks and inactive instances.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    root = FakeNode()
    setup = root.add("setup", FakeNode())
    collection = setup.add("collection", FakeNode(names=["active", "inactive"]))
    collection.add("active", FakeNode(state={"value": 1}))
    collection.add("inactive", FakeNode(active=False, state={"value": 2}))

    class KeysOnly(FakeNode):
        def get_object_names(self):
            """Return the object names.

            Returns
            -------
            None
                The function completes through its side effects.
            """
            raise RuntimeError("no get_object_names")

    keys_only = setup.add("keys_only", KeysOnly(names=["k1"]))
    keys_only.add("k1", FakeNode(state={"key": 1}))
    setup.add("bad_names", FakeNode())

    result = introspection.collect_targeted_context(
        root,
        paths_to_check=["setup.collection"],
        named_object_types=["setup.keys_only", "setup.bad_names", "setup.missing"],
        instance_state_fetch=[
            "setup.collection[active]",
            "setup.collection/inactive",
            "malformed-fetch",
            "setup.collection/missing",
        ],
    )

    assert result["state_values"].get("setup.collection") is None
    assert result["named_objects"]["setup.keys_only"] == ["k1"]
    assert result["named_objects"]["setup.bad_names"] == []
    assert result["named_objects"]["setup.missing"] == []
    assert result["active_status"]["setup.collection[active]"] is True
    assert result["state_values"]["setup.collection[active]"] == {"value": 1}
    assert result["active_status"]["setup.collection/inactive"] is False
    assert result["state_values"]["setup.collection/inactive"] == {"inactive": True}


def test_phase_property_probe_uses_standard_and_utl_boundary_roots():
    """Verify that phase property probe uses standard and utl boundary roots.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    root = FakeNode()
    setup = root.add("setup", FakeNode())
    models = setup.add("models", FakeNode())
    models.add("multiphase", FakeNode(state={"model": "vof"}))
    bcs = setup.add("boundary_conditions", FakeNode())
    velocity_inlet = bcs.add("velocity_inlet", FakeNode(names=["inlet-1"]))
    inlet = velocity_inlet.add("inlet-1", FakeNode())
    phase_collection = inlet.add("phase", FakeNode(names=["phase-1", "mixture"]))
    phase_collection.add("phase-1", FakeNode(child_names=["momentum", "thermal"]))
    phase_collection.add("mixture", FakeNode(child_names=["volume_fraction"]))

    context = introspection.collect_targeted_context(
        root,
        paths_to_check=["setup.models.multiphase"],
        named_object_types=["setup.models.multiphase.phases"],
    )
    assert context["phase_property_map"] == {}

    phase_names = {"setup.models.multiphase.phases": ["phase-1"]}
    state_values = {"setup.models.multiphase": {"model": "vof"}}
    assert introspection._probe_phase_properties(root, state_values, phase_names) == {
        "phase-1": ["momentum", "thermal"],
        "mixture": ["volume_fraction"],
    }

    utl_root = FakeNode()
    utl_setup = utl_root.add("setup", FakeNode())
    physics = utl_setup.add("physics", FakeNode())
    boundaries = physics.add("boundaries", FakeNode())
    outlet_collection = boundaries.add("pressure_outlet", FakeNode(names=["outlet-1"]))
    outlet = outlet_collection.add("outlet-1", FakeNode())
    outlet_phases = outlet.add("phase", FakeNode(names=["phase-1"]))
    outlet_phases.add("phase-1", FakeNode(child_names=["backflow"]))
    assert introspection._probe_phase_properties(utl_root, state_values, phase_names) == {
        "phase-1": ["backflow"]
    }
