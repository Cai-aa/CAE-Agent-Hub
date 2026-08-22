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

import ast
import asyncio
import builtins
from pathlib import Path
import sys
import threading
from types import SimpleNamespace

import pytest

import ansys.fluent
from ansys.fluent.mcp.common.errors import InvalidArgumentsError, NotConnectedError
from ansys.fluent.mcp.common.models import RunCodeResult
from ansys.fluent.mcp.solve.backends import pyfluent


def test_extract_settings_paths_from_attribute_and_call_chains():
    """Verify that extract settings paths from attribute and call chains.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    tree = ast.parse(
        """
solver.settings.setup.models.energy.enabled = True
value = solver.settings.solution.methods.p_v_coupling.flow_scheme
solver.settings.solution.initialization.hybrid_initialize()
fluid["elbow-fluid"].general.material = "water"
setup.materials.fluid["air"].general.material += "-mix"
        """
    )

    paths = set(pyfluent._extract_settings_paths(tree))

    assert "setup.models.energy.enabled" in paths
    assert "solution.methods.p_v_coupling.flow_scheme" in paths
    assert "solution.initialization.hybrid_initialize" in paths
    assert "setup.materials.fluid.general.material" in paths
    assert "general.material" not in paths


def test_dead_channel_classifier_matches_common_transport_errors():
    """Verify that dead channel classifier matches common transport errors.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    assert pyfluent._looks_like_dead_channel(RuntimeError("Server not running")) is True
    assert pyfluent._looks_like_dead_channel(ConnectionError("connection reset by peer")) is True
    assert pyfluent._looks_like_dead_channel(ValueError("ordinary validation failure")) is False


def test_resolve_fluent_launch_config_normalizes_supported_values():
    """Verify that resolve fluent launch config normalizes supported values.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    config = pyfluent.resolve_fluent_launch_config(
        dimension="3d",
        mode="aero",
        gpu="0,1",
        journal_file_names=[" first.jou ", ""],
        ui_mode="no_gui",
    )

    assert config["dimension"] == 3
    assert config["mode"] == "solver_aero"
    assert config["gpu"] == [0, 1]
    assert config["journal_file_names"] == ["first.jou"]
    assert config["ui_mode"] == "no_gui"

    full = pyfluent.resolve_fluent_launch_config(
        product_version="26.2",
        case_file_name="case.cas.h5",
        case_data_file_name="case.dat.h5",
        cwd="work",
        fluent_path="fluent.exe",
        env={"A": "B"},
        graphics_driver="null",
        scheduler_options={"queue": "debug"},
        start_timeout=12,
        cleanup_on_exit=True,
        additional_arguments="-driver null",
    )
    assert full == {
        "precision": "double",
        "processor_count": 1,
        "ui_mode": "gui",
        "dimension": 3,
        "product_version": "26.2",
        "case_file_name": "case.cas.h5",
        "case_data_file_name": "case.dat.h5",
        "cwd": "work",
        "fluent_path": "fluent.exe",
        "env": {"A": "B"},
        "graphics_driver": "null",
        "scheduler_options": {"queue": "debug"},
        "start_timeout": 12,
        "cleanup_on_exit": True,
        "additional_arguments": "-driver null",
    }


@pytest.mark.parametrize(
    "kwargs",
    [
        {"dimension": True},
        {"dimension": 2, "gpu": True},
        {"dimension": 3, "gpu": True, "mode": "meshing"},
        {"mode": "invalid"},
        {"gpu": "abc"},
    ],
)
def test_resolve_fluent_launch_config_rejects_invalid_values(kwargs):
    """Verify that resolve fluent launch config rejects invalid values.

    Parameters
    ----------
    kwargs : Any
        Keyword arguments forwarded to the callable.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    with pytest.raises(ValueError):
        pyfluent.resolve_fluent_launch_config(**kwargs)


def test_launch_normalizers_cover_none_and_type_errors():
    """Verify that launch normalizers cover none and type errors.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    assert pyfluent._normalise_mode(None) is None
    assert pyfluent._normalise_mode("prepost") == "pre_post"
    assert pyfluent._normalise_gpu(False) is False
    assert pyfluent._normalise_journal_names("  ") is None
    assert pyfluent._normalise_journal_names([" "]) is None

    with pytest.raises(ValueError):
        pyfluent._normalise_dimension(4)
    with pytest.raises(ValueError):
        pyfluent._normalise_dimension("4d")
    with pytest.raises(ValueError):
        pyfluent._normalise_mode(3)
    with pytest.raises(ValueError):
        pyfluent._normalise_gpu(object())


def test_filter_launch_kwargs_uses_callable_signature():
    """Verify that filter launch kwargs uses callable signature.

    Returns
    -------
    None
        The function completes through its side effects.
    """

    def launch_fluent(precision, processor_count=1):
        """Exercise the launch fluent test helper.

        Parameters
        ----------
        precision : Any
            Solver precision requested for the Fluent session.
        processor_count : Any
            Number of processors requested for the Fluent session.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        return precision, processor_count

    filtered = pyfluent._filter_launch_kwargs(
        launch_fluent,
        {"precision": "double", "processor_count": 4, "unknown": "drop", "mode": None},
    )

    assert filtered == {"precision": "double", "processor_count": 4}


class FamilyNode:
    def __init__(self, names, state=None, item_states=None, fail_state=False):
        """Initialize the FamilyNode instance.

        Parameters
        ----------
        names : Any
            Object names supplied to the helper.
        state : Any
            State to supply to the function.
        item_states : Any
            Item states to supply to the function.
        fail_state : Any
            Fail state to supply to the function.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        self._names = names
        self._state = state
        self._item_states = item_states or {}
        self._fail_state = fail_state

    def get_object_names(self):
        """Return the object names.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        return list(self._names)

    def get_state(self):
        """Return the state.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        if self._fail_state:
            raise RuntimeError("inactive")
        return self._state

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
        return SimpleNamespace(get_state=lambda: self._item_states[key])


class FailingItemFamily(FamilyNode):
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
        if key == "bad":
            raise RuntimeError("bad item")
        return super().__getitem__(key)


def test_read_family_state_handles_empty_batch_and_chunked_paths(monkeypatch):
    """Verify that read family state handles empty batch and chunked paths.

    Parameters
    ----------
    monkeypatch : Any
        Pytest fixture used to patch environment variables or dependencies.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    assert pyfluent._read_family_state(None) == {}
    assert pyfluent._read_family_state(FamilyNode([], state={"unused": True})) == {}
    assert pyfluent._read_family_state(FamilyNode(["a"], state={"a": {"x": 1}})) == {"a": {"x": 1}}
    assert pyfluent._read_family_state(FamilyNode(["a"], state=["not", "dict"])) == {}
    assert pyfluent._read_family_state(FamilyNode(["a"], fail_state=True)) == {}

    monkeypatch.setenv("FLUIDS_MCP_BATCH_FAMILY_LIMIT", "1")
    chunked = pyfluent._read_family_state(
        FamilyNode(["a", "b", "c"], item_states={"a": {"x": 1}, "b": ["skip"], "c": {"z": 3}})
    )
    assert chunked == {"a": {"x": 1}, "c": {"z": 3}}

    skipped = pyfluent._read_family_state(
        FailingItemFamily(["ok", "bad"], item_states={"ok": {"x": 1}, "bad": {"lost": True}})
    )
    assert skipped == {"ok": {"x": 1}}

    monkeypatch.setenv("FLUIDS_MCP_BATCH_FAMILY_LIMIT", "bad")
    assert pyfluent._batch_family_limit() == 5000
    monkeypatch.setenv("FLUIDS_MCP_BATCH_FAMILY_LIMIT", "0")
    assert pyfluent._batch_family_limit() == 0


def test_safe_builtins_allow_whitelisted_imports_and_block_unsafe_ones():
    """Verify that safe builtins allow whitelisted imports and block unsafe ones.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    safe_import = pyfluent._make_safe_import()

    assert safe_import("math").sqrt(4) == 2
    with pytest.raises(ImportError):
        safe_import("os")
    with pytest.raises(ImportError):
        safe_import("math", level=1)

    builtins = pyfluent._build_safe_builtins()
    assert "__import__" in builtins
    assert "eval" not in builtins


def test_filter_launch_kwargs_for_var_kwargs_and_uninspectable_callables():
    """Verify that filter launch kwargs for var kwargs and uninspectable callables.

    Returns
    -------
    None
        The function completes through its side effects.
    """

    def launch_fluent(**kwargs):
        """Exercise the launch fluent test helper.

        Parameters
        ----------
        kwargs : Any
            Keyword arguments forwarded to the callable.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        return kwargs

    assert pyfluent._filter_launch_kwargs(launch_fluent, {"a": 1, "b": None}) == {"a": 1}
    assert pyfluent._normalise_dimension(None) is None
    assert pyfluent._normalise_gpu(2) == [2]
    assert pyfluent._normalise_gpu("") is True
    assert pyfluent._normalise_journal_names((" a.jou ", "")) == ["a.jou"]
    with pytest.raises(ValueError):
        pyfluent._normalise_journal_names(123)
    with pytest.raises(ValueError):
        pyfluent._normalise_gpu(["x"])

    class Uninspectable:
        @property
        def __signature__(self):
            """Exercise the signature test helper.

            Returns
            -------
            None
                The function completes through its side effects.
            """
            raise ValueError("no signature")

        def __call__(self, **kwargs):
            """Invoke the fake callable for the test.

            Parameters
            ----------
            kwargs : Any
                Keyword arguments forwarded to the callable.

            Returns
            -------
            None
                The function completes through its side effects.
            """
            return kwargs

    assert pyfluent._filter_launch_kwargs(Uninspectable(), {"a": 1, "b": None}) == {"a": 1}


def test_pyfluent_backend_basic_helpers_and_metadata_methods():
    """Verify that pyfluent backend basic helpers and metadata methods.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    backend = pyfluent.PyFluentBackend()
    with pytest.raises(NotConnectedError):
        backend._require()

    named_expressions = SimpleNamespace(get_object_names=lambda: ["expr"])
    attrs_node = SimpleNamespace(
        get_attrs=lambda attrs: {"active?": True, "user-creatable?": False}
    )
    allowed_node = SimpleNamespace(allowed_values=lambda: ["a", "b"])
    root = SimpleNamespace(
        setup=SimpleNamespace(
            named_expressions=named_expressions, attrs_node=attrs_node, allowed_node=allowed_node
        )
    )
    backend._solver = SimpleNamespace(
        settings=root, scheme=SimpleNamespace(eval=lambda _expr: True)
    )

    assert backend.is_connected() is True
    assert backend._settings_root() is root
    assert backend._probe_live_named_for_guard() == {"setup.named_expressions": ["expr"]}
    assert backend._probe_iterating_for_guard() is True
    assert asyncio.run(backend.get_allowed_values(["setup.allowed_node", "missing"])) == {
        "setup.allowed_node": ["a", "b"],
        "missing": [],
    }
    assert asyncio.run(backend.get_node_attrs(["setup.attrs_node", "missing"], ["active?"])) == {
        "setup.attrs_node": {"active?": True, "user-creatable?": False},
        "missing": {},
    }
    assert asyncio.run(backend.get_node_attrs_bulk("setup.attrs_node", ["active?"])) == {}

    with pytest.raises(InvalidArgumentsError):
        asyncio.run(backend.get_allowed_values([]))
    with pytest.raises(InvalidArgumentsError):
        asyncio.run(backend.get_node_attrs([], ["active?"]))
    with pytest.raises(InvalidArgumentsError):
        asyncio.run(backend.get_node_attrs(["setup.attrs_node"], []))

    backend._mark_solver_disconnected()
    assert backend.is_connected() is False


class FakeScheme:
    def __init__(self, values=None, raises=False):
        """Initialize the FakeScheme instance.

        Parameters
        ----------
        values : Any
            Values to supply to the function.
        raises : Any
            Raises to supply to the function.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        self.values = values or {}
        self.raises = raises
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
        if self.raises:
            raise RuntimeError("scheme unavailable")
        return self.values.get(expr, True)


class FakeSettingsNode:
    def __init__(self, *, state=None, attrs=None, active=True, allowed=None, child_names=None):
        """Initialize the FakeSettingsNode instance.

        Parameters
        ----------
        state : Any
            State to supply to the function.
        attrs : Any
            Attrs to supply to the function.
        active : Any
            Active to supply to the function.
        allowed : Any
            Allowed to supply to the function.
        child_names : Any
            Child names to supply to the function.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        self._state = state
        self._attrs = attrs or {}
        self._active = active
        self._allowed = allowed
        self.child_names = list(child_names or [])

    def get_state(self):
        """Return the state.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        if isinstance(self._state, Exception):
            raise self._state
        return self._state

    def get_attrs(self, attrs, recursive=False):
        """Return the attrs.

        Parameters
        ----------
        attrs : Any
            Attrs to supply to the function.
        recursive : Any
            Recursive to supply to the function.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        if recursive:
            return self._attrs.get("recursive", {})
        return {attr: self._attrs[attr] for attr in attrs if attr in self._attrs}

    def is_active(self):
        """Return whether active.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        return self._active

    def allowed_values(self):
        """Return allowed values for the fake setting.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        if isinstance(self._allowed, Exception):
            raise self._allowed
        return list(self._allowed or [])


class FakeNamedCollection(FakeSettingsNode):
    def __init__(self, names, *, items=None, state=None, attrs=None, child_object_type=None):
        """Initialize the FakeNamedCollection instance.

        Parameters
        ----------
        names : Any
            Object names supplied to the helper.
        items : Any
            Items to supply to the function.
        state : Any
            State to supply to the function.
        attrs : Any
            Attrs to supply to the function.
        child_object_type : Any
            Child object type to supply to the function.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        super().__init__(state=state, attrs=attrs)
        self._names = list(names)
        self._items = items or {}
        self.child_object_type = child_object_type

    def get_object_names(self):
        """Return the object names.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        return list(self._names)

    def keys(self):
        """Return the configured mapping keys.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        return self._items.keys()

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
        return self._items[key]


def test_pyfluent_connect_import_failure_launch_failure_and_close_fallback(monkeypatch):
    """Verify that pyfluent connect import failure launch failure and close fallback.

    Parameters
    ----------
    monkeypatch : Any
        Pytest fixture used to patch environment variables or dependencies.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    monkeypatch.delitem(sys.modules, "ansys.fluent.core", raising=False)

    original_import = builtins.__import__

    def blocked_core_import(name, globals=None, locals=None, fromlist=(), level=0):
        """Exercise the blocked core import test helper.

        Parameters
        ----------
        name : Any
            Name of the object, module, or setting being processed.
        globals : Any
            Globals mapping supplied by Python's import machinery.
        locals : Any
            Locals mapping supplied by Python's import machinery.
        fromlist : Any
            Names requested by a ``from ... import ...`` statement.
        level : Any
            Logging level or severity to apply.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        if name == "ansys.fluent.core":
            raise ImportError("blocked ansys.fluent.core")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", blocked_core_import)
    backend = pyfluent.PyFluentBackend()
    missing = asyncio.run(backend.connect())
    assert missing.status == "error"
    assert missing.error_code == "pyfluent_not_installed"
    monkeypatch.setattr(builtins, "__import__", original_import)

    def launch_fluent(**_kwargs):
        """Exercise the launch fluent test helper.

        Parameters
        ----------
        _kwargs : Any
            Keyword arguments forwarded to the wrapped call.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        raise RuntimeError("launch failed")

    fake_core = SimpleNamespace(
        launch_fluent=launch_fluent, connect_to_fluent=lambda **_kwargs: None
    )
    monkeypatch.setitem(sys.modules, "ansys.fluent.core", fake_core)
    monkeypatch.setattr(ansys.fluent, "core", fake_core, raising=False)
    failed = asyncio.run(backend.connect())
    assert failed.status == "error"
    assert failed.error_code == "pyfluent_connect_failed"

    class LaunchedSession:
        def __init__(self):
            self.exited = False

        def exit(self):
            self.exited = True

    launched = LaunchedSession()
    launch_started = threading.Event()
    release_launch = threading.Event()

    def blocking_launch_fluent(**_kwargs):
        launch_started.set()
        release_launch.wait(timeout=5)
        return launched

    fake_core.launch_fluent = blocking_launch_fluent
    cancel_backend = pyfluent.PyFluentBackend()

    async def cancel_connect_after_launch_starts():
        task = asyncio.create_task(cancel_backend.connect(mode="meshing"))
        await asyncio.to_thread(launch_started.wait, 5)
        task.cancel()
        release_launch.set()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(cancel_connect_after_launch_starts())
    assert launched.exited is True
    assert cancel_backend._solver is None
    assert cancel_backend._session_kind == "solver_session"

    class CloseOnlySession:
        def __init__(self, fail=False):
            """Initialize the CloseOnlySession instance.

            Parameters
            ----------
            fail : Any
                Whether the test double should simulate a failure.

            Returns
            -------
            None
                The function completes through its side effects.
            """
            self.closed = False
            self.fail = fail

        def close(self):
            """Close resources for the CloseOnlySession object.

            Returns
            -------
            None
                The function completes through its side effects.
            """
            self.closed = True
            if self.fail:
                raise RuntimeError("close failed")

    closing = CloseOnlySession()
    backend._solver = closing
    backend.endpoint = "pyfluent://local:launched"
    asyncio.run(backend.disconnect())
    assert closing.closed is True
    assert backend.endpoint is None

    failing = CloseOnlySession(fail=True)
    backend._solver = failing
    backend.endpoint = "pyfluent://local:launched"
    backend.close_sync()
    assert failing.closed is True
    assert backend._solver is None


def test_pyfluent_guard_probe_failure_paths():
    """Verify that pyfluent guard probe failure paths.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    backend = pyfluent.PyFluentBackend()
    assert backend._probe_live_named_for_guard() == {}
    assert backend._probe_iterating_for_guard() is False

    backend._solver = SimpleNamespace(
        settings=SimpleNamespace(setup=SimpleNamespace()), scheme=None
    )
    assert backend._probe_live_named_for_guard() == {}
    assert backend._probe_iterating_for_guard() is False

    failing_named = SimpleNamespace(
        get_object_names=lambda: (_ for _ in ()).throw(RuntimeError("inactive"))
    )
    backend._solver = SimpleNamespace(
        settings=SimpleNamespace(setup=SimpleNamespace(named_expressions=failing_named)),
        scheme=FakeScheme(raises=True),
    )
    assert backend._probe_live_named_for_guard() == {}
    assert backend._probe_iterating_for_guard() is False


def test_pyfluent_live_context_methods_with_fake_settings_tree(monkeypatch):
    """Verify that pyfluent live context methods with fake settings tree.

    Parameters
    ----------
    monkeypatch : Any
        Pytest fixture used to patch environment variables or dependencies.

    Returns
    -------
    None
        The function completes through its side effects.
    """

    class CommandArgBase:
        pass

    class String(CommandArgBase):
        def allowed_values(self):
            """Return allowed values for the fake setting.

            Returns
            -------
            None
                The function completes through its side effects.
            """
            return ["fast", "accurate"]

    class FakeCommand:
        argument_names = ("mode",)

        def __init__(self):
            """Initialize the FakeCommand instance.

            Returns
            -------
            None
                The function completes through its side effects.
            """
            self.mode = String()

        def __call__(self, **_kwargs):
            """Invoke the fake callable for the test.

            Parameters
            ----------
            _kwargs : Any
                Keyword arguments forwarded to the wrapped call.

            Returns
            -------
            None
                The function completes through its side effects.
            """
            return None

    class EmptyCommand:
        argument_names = ()

    class BadCommand:
        @property
        def argument_names(self):
            """Exercise the argument names test helper.

            Returns
            -------
            None
                The function completes through its side effects.
            """
            return 5

    class QueryCommand(FakeCommand):
        pass

    class ChildTemplate:
        child_names = ["kind", "roughness"]

    class StaticString:
        pass

    class StaticTemplate:
        child_names = ["static_field", "unknown_field"]
        static_field = StaticString

    instance = SimpleNamespace(
        kind=FakeSettingsNode(attrs={"allowed-values": ["wall"], "active?": True}),
        roughness=FakeSettingsNode(
            attrs={"min": 0, "max": 1, "default": 0.2, "units-quantity": "length"}
        ),
    )
    wall = FakeNamedCollection(
        ["hot-wall"],
        items={"hot-wall": instance},
        state={"hot-wall": {"thermal": {"thermal_condition": "Coupled"}}},
        attrs={
            "active?": True,
            "user-creatable?": True,
            "recursive": {"child": {"active?": False}},
        },
        child_object_type=ChildTemplate,
    )
    wall.create = SimpleNamespace(argument_names=("name",))
    inlet = FakeNamedCollection([], items={})
    static_family = FakeNamedCollection([], child_object_type=StaticTemplate)
    setup = SimpleNamespace(
        boundary_conditions=SimpleNamespace(wall=wall, velocity_inlet=inlet, outlet=static_family),
        command=FakeCommand(),
        empty_command=EmptyCommand(),
        bad_command=BadCommand(),
        query=QueryCommand(),
        leaf=FakeSettingsNode(
            state={"value": 3}, attrs={"active?": False}, active=False, allowed=["a", "b"]
        ),
        group=FakeSettingsNode(child_names=["leaf"]),
    )
    root = SimpleNamespace(setup=setup)
    backend = pyfluent.PyFluentBackend()
    backend._solver = SimpleNamespace(
        settings=root, scheme=FakeScheme(values={"(%cx-is-solution-iterating)": False})
    )

    monkeypatch.setattr(pyfluent, "discover_named_objects_via_scheme", lambda _solver: None)
    monkeypatch.setattr(
        pyfluent,
        "discover_named_objects_via_walk",
        lambda _root: {
            "setup/boundary-conditions/wall": ["hot-wall"],
            "setup/boundary-conditions/velocity-inlet": [],
        },
    )

    names = asyncio.run(backend.list_named_objects())
    assert names["setup/boundary-conditions/wall"] == ["hot-wall"]
    assert asyncio.run(backend.list_named_objects()) is names
    assert asyncio.run(backend.get_named_object_names("setup.boundary_conditions.wall")) == [
        "hot-wall"
    ]
    assert asyncio.run(backend.get_named_object_names("setup.boundary_conditions.wall")) == [
        "hot-wall"
    ]
    assert asyncio.run(backend.get_named_object_names("setup.missing")) == []
    assert asyncio.run(backend.get_allowed_values(["setup.leaf", "setup.missing"])) == {
        "setup.leaf": ["a", "b"],
        "setup.missing": [],
    }
    state = asyncio.run(backend.get_state(["setup.leaf", "setup.missing"]))
    assert state["setup.leaf"] == {"inactive": True}
    assert "error" in state["setup.missing"]
    assert asyncio.run(backend.get_active_status(["setup.leaf", "setup.missing"])) == {
        "setup.leaf": False,
        "setup.missing": False,
    }
    assert asyncio.run(
        backend.get_node_attrs_bulk("setup.boundary_conditions.wall", ["active?"])
    ) == {"child": {"active?": False}}
    assert asyncio.run(
        backend.probe_path(
            [
                "setup.command",
                "setup.query",
                "setup.boundary_conditions.wall",
                "setup.leaf",
                "setup.group",
                "setup.missing",
            ]
        )
    ) == {
        "setup.command": {
            "exists": True,
            "is_active": True,
            "is_user_creatable": False,
            "kind": "command",
        },
        "setup.query": {
            "exists": True,
            "is_active": True,
            "is_user_creatable": False,
            "kind": "query",
        },
        "setup.boundary_conditions.wall": {
            "exists": True,
            "is_active": True,
            "is_user_creatable": True,
            "kind": "named_object",
        },
        "setup.leaf": {
            "exists": True,
            "is_active": False,
            "is_user_creatable": False,
            "kind": "leaf",
        },
        "setup.group": {
            "exists": True,
            "is_active": True,
            "is_user_creatable": False,
            "kind": "group",
        },
        "setup.missing": {"exists": False, "kind": "missing"},
    }

    signature = asyncio.run(backend.get_command_arguments("setup.command"))
    assert signature["argument_names"] == ["mode"]
    assert signature["arguments"]["mode"]["allowed_values"] == ["fast", "accurate"]
    assert asyncio.run(backend.get_command_arguments("setup.empty_command")) == {
        "argument_names": [],
        "arguments": {},
    }
    assert asyncio.run(backend.get_command_arguments("setup.bad_command")) is None
    assert asyncio.run(backend.get_command_arguments("setup.leaf")) is None
    assert asyncio.run(backend.get_command_arguments("setup.missing")) is None

    template = asyncio.run(backend.describe_named_object_template("setup.boundary_conditions.wall"))
    assert template["child_class"] == "ChildTemplate"
    assert template["create_command"] == {"argument_names": ["name"]}
    assert template["fields"]["kind"]["allowed_values"] == ["wall"]
    assert template["fields"]["roughness"]["units"] == "length"
    static_template = asyncio.run(
        backend.describe_named_object_template("setup.boundary_conditions.outlet")
    )
    assert static_template["fields"]["static_field"]["type_hint"] == "StaticString"
    assert static_template["fields"]["unknown_field"]["type_hint"] == "unknown"
    assert asyncio.run(backend.describe_named_object_template("setup.leaf")) is None
    assert asyncio.run(backend.describe_named_object_template("setup.missing")) is None

    context = asyncio.run(
        backend.get_targeted_context(
            paths_to_check=["setup.leaf"],
            named_object_types=["setup.boundary_conditions.wall"],
            instance_state_fetch=["setup.boundary_conditions.wall/hot-wall"],
        )
    )
    assert context["active_status"]["setup.leaf"] is False
    assert "setup.leaf" not in context["state_values"]
    with pytest.raises(InvalidArgumentsError):
        asyncio.run(backend.probe_path([]))
    with pytest.raises(InvalidArgumentsError):
        asyncio.run(backend.get_targeted_context(paths_to_check=[]))


def test_get_command_arguments_skips_allowed_values_on_inactive_argument(monkeypatch):
    """Inactive command arguments must not trigger an ``allowed_values()``
    readout — the Scheme side prints ``api-get-attrs: the object is not
    active`` into Fluent's transcript before Python can swallow the
    exception. Batched ``get_attrs(["active?", "allowed-values"])`` lets
    us gate on ``active?`` in the same RPC."""

    calls: dict[str, list] = {"allowed_values": [], "get_attrs": []}

    class BatchedArg:
        """Fake command argument that supports batched ``get_attrs``."""

        def __init__(self, *, active, allowed):
            self._active = active
            self._allowed = allowed

        def get_attrs(self, attrs, recursive=False):  # noqa: ARG002
            calls["get_attrs"].append(tuple(attrs))
            raw = {}
            if "active?" in attrs:
                raw["active?"] = self._active
            if "allowed-values" in attrs and self._active:
                raw["allowed-values"] = list(self._allowed)
            return raw

        def allowed_values(self):
            calls["allowed_values"].append(True)
            return list(self._allowed)

    class FakeCommand:
        argument_names = ("method", "normal_computation_method")

        def __init__(self):
            self.method = BatchedArg(active=True, allowed=["yz-plane", "point-and-normal"])
            self.normal_computation_method = BatchedArg(
                active=False, allowed=["front-only", "back-only"]
            )

    root = SimpleNamespace(
        setup=SimpleNamespace(command=FakeCommand()),
    )
    backend = pyfluent.PyFluentBackend()
    backend._solver = SimpleNamespace(settings=root)

    signature = asyncio.run(backend.get_command_arguments("setup.command"))

    assert signature is not None
    args = signature["arguments"]
    assert args["method"]["is_active"] is True
    assert args["method"]["allowed_values"] == ["yz-plane", "point-and-normal"]
    assert args["normal_computation_method"]["is_active"] is False
    assert "allowed_values" not in args["normal_computation_method"]
    assert calls["allowed_values"] == []
    assert calls["get_attrs"] == [
        ("active?", "allowed-values"),
        ("active?", "allowed-values"),
    ]


def test_pyfluent_command_call_diagnostics_for_commands_named_families_and_leaves():
    """Verify that pyfluent command call diagnostics for commands named families and leaves.

    Returns
    -------
    None
        The function completes through its side effects.
    """

    class String:
        def allowed_values(self):
            """Return allowed values for the fake setting.

            Returns
            -------
            None
                The function completes through its side effects.
            """
            return ["fast", "accurate"]

    class FakeCommand:
        argument_names = ("mode",)

        def __init__(self):
            """Initialize the FakeCommand instance.

            Returns
            -------
            None
                The function completes through its side effects.
            """
            self.mode = String()

    class Family:
        def get_object_names(self):
            """Return the object names.

            Returns
            -------
            None
                The function completes through its side effects.
            """
            return ["wall-1", "wall-2"]

    class Leaf:
        pass

    root = SimpleNamespace(
        setup=SimpleNamespace(
            command=FakeCommand(),
            family=Family(),
            leaf=Leaf(),
        )
    )
    backend = pyfluent.PyFluentBackend()
    backend._solver = SimpleNamespace(settings=root)

    command_hint = backend._diagnose_command_call_error(
        "solver.settings.setup.command('fast')",
        TypeError("__call__() takes 1 positional argument"),
    )
    family_hint = backend._diagnose_command_call_error(
        "solver.settings.setup.family('wall-1')",
        AttributeError("'_has_migration_adapter' missing"),
    )
    session_root_hint = backend._diagnose_command_call_error(
        "session()",
        AttributeError("'_has_migration_adapter' missing"),
    )
    leaf_hint = backend._diagnose_command_call_error(
        "solver.settings.setup.leaf('x')",
        AttributeError("'_has_migration_adapter' missing"),
    )

    assert "is a Command" in command_hint
    assert "mode (String) allowed=['fast', 'accurate']" in command_hint
    assert "NamedObject family" in family_hint
    assert "wall-1" in family_hint
    assert "not a function" in leaf_hint
    assert "'session' is a SimpleNamespace settings node" in session_root_hint
    assert (
        backend._diagnose_command_call_error("not python (", TypeError("__call__() broken")) is None
    )
    assert (
        backend._diagnose_command_call_error(
            "solver.settings.setup.command()", ValueError("ordinary")
        )
        is None
    )
    assert (
        backend._diagnose_command_call_error(
            "factory().setup.command()", TypeError("__call__() broken")
        )
        is None
    )
    assert (
        backend._diagnose_command_call_error(
            "solver.settings.setup.missing()", TypeError("__call__() broken")
        )
        is None
    )

    backend._solver = None
    assert (
        backend._diagnose_command_call_error(
            "solver.settings.setup.command()", TypeError("__call__() broken")
        )
        is None
    )


def test_pyfluent_mesh_adjacency_fields_and_status_helpers():
    """Verify that pyfluent mesh adjacency fields and status helpers.

    Returns
    -------
    None
        The function completes through its side effects.
    """

    class Face:
        def __init__(self, adjacent, shadow=None):
            """Initialize the Face instance.

            Parameters
            ----------
            adjacent : Any
                Adjacent to supply to the function.
            shadow : Any
                Shadow to supply to the function.

            Returns
            -------
            None
                The function completes through its side effects.
            """
            self._adjacent = adjacent
            self._shadow = shadow

        def adjacent_cell_zone(self):
            """Exercise the adjacent cell zone test helper.

            Returns
            -------
            None
                The function completes through its side effects.
            """
            return self._adjacent

        def shadow_face_zone(self):
            """Exercise the shadow face zone test helper.

            Returns
            -------
            None
                The function completes through its side effects.
            """
            return self._shadow

    wall = FakeNamedCollection(
        ["hot-wall", "hot-wall-shadow"],
        items={"hot-wall": Face("fluid", "hot-wall-shadow"), "hot-wall-shadow": Face("solid")},
        state={
            "hot-wall": {"thermal": {"thermal_condition": "Coupled"}},
            "hot-wall-shadow": {"thermal": {"thermal_condition": "Fixed Temperature"}},
        },
    )
    inlet = FakeNamedCollection(["inlet"], items={"inlet": Face("fluid")}, state={"inlet": {}})
    setup = SimpleNamespace(
        boundary_conditions=SimpleNamespace(wall=wall, velocity_inlet=inlet),
        general=SimpleNamespace(solver=FakeSettingsNode(state={"time": "unsteady-2nd-order"})),
    )
    solution = SimpleNamespace(
        initialization=SimpleNamespace(is_initialized=lambda: True),
        run_calculation=FakeSettingsNode(state={"iter_count": 12}),
    )
    root = SimpleNamespace(setup=setup, solution=solution)
    fields = SimpleNamespace(get_scalar_field_info=lambda: {"pressure": {}, "velocity": {}})
    backend = pyfluent.PyFluentBackend()
    backend._solver = SimpleNamespace(
        settings=root, field_info=fields, scheme=FakeScheme(values={})
    )

    assert asyncio.run(backend.mesh_adjacency_probe(["fluid", "solid"])) == {
        "fluid": ["hot-wall", "hot-wall-shadow", "inlet"],
        "solid": ["hot-wall", "hot-wall-shadow"],
    }
    assert asyncio.run(backend.mesh_adjacency_probe([])) == {}
    assert asyncio.run(backend.list_fields()) == {
        "fields": ["pressure", "velocity"],
        "scope": "any",
        "source": "get_scalar_field_info",
    }
    status = asyncio.run(backend.solver_status())
    assert status["initialized"] is True
    assert status["iterations"] == 12
    assert status["solver_mode"] == "transient"
    assert status["utl_enabled"] is False

    broken_backend = pyfluent.PyFluentBackend()
    broken_backend._solver = SimpleNamespace(settings=SimpleNamespace())
    broken_status = asyncio.run(broken_backend.solver_status())
    assert broken_status == {"initialized": None, "utl_enabled": False}


def test_pyfluent_mesh_adjacency_and_field_failure_fallbacks():
    """Verify that pyfluent mesh adjacency and field failure fallbacks.

    Returns
    -------
    None
        The function completes through its side effects.
    """

    class RaisingNames(FakeNamedCollection):
        def get_object_names(self):
            """Return the object names.

            Returns
            -------
            None
                The function completes through its side effects.
            """
            raise RuntimeError("inactive family")

    class MissingFace:
        adjacent_cell_zone = None
        shadow_face_zone = None

    wall = FakeNamedCollection(
        ["bad-wall", "plain-wall", "no-shadow"],
        items={
            "bad-wall": MissingFace(),
            "plain-wall": MissingFace(),
            "no-shadow": MissingFace(),
        },
        state={
            "bad-wall": ["skip"],
            "plain-wall": {"thermal": "not-dict"},
            "no-shadow": {"thermal": {"thermal_condition": "Coupled"}},
        },
    )
    setup = SimpleNamespace(
        boundary_conditions=SimpleNamespace(wall=wall, velocity_inlet=RaisingNames(["x"]))
    )
    backend = pyfluent.PyFluentBackend()
    backend._solver = SimpleNamespace(
        settings=SimpleNamespace(setup=setup), fields_info=SimpleNamespace()
    )

    assert asyncio.run(backend.mesh_adjacency_probe(["fluid"], bc_filter=("wall", "unknown"))) == {
        "fluid": []
    }

    backend._solver = SimpleNamespace(settings=SimpleNamespace(setup=SimpleNamespace()))
    with pytest.raises(pyfluent.BackendUnavailableError):
        asyncio.run(backend.mesh_adjacency_probe(["fluid"]))

    backend._solver = SimpleNamespace(
        fields_info=SimpleNamespace(get_fields_info=lambda: {"z": {}, "a": {}})
    )
    assert asyncio.run(backend.list_fields(scope="cell")) == {
        "fields": ["a", "z"],
        "scope": "cell",
        "source": "get_fields_info",
    }
    backend._solver = SimpleNamespace(
        fields=SimpleNamespace(
            get_scalar_field_info=lambda: (_ for _ in ()).throw(RuntimeError("nope"))
        )
    )
    assert asyncio.run(backend.list_fields()) is None


def test_pyfluent_run_code_validate_help_mesh_reports_and_screenshot(monkeypatch):
    """Verify that pyfluent run code validate help mesh reports and screenshot.

    Parameters
    ----------
    monkeypatch : Any
        Pytest fixture used to patch environment variables or dependencies.

    Returns
    -------
    None
        The function completes through its side effects.
    """
    backend = pyfluent.PyFluentBackend()
    backend._solver = SimpleNamespace(settings=SimpleNamespace(), scheme=FakeScheme(values={}))

    result = asyncio.run(backend.run_code("x = 2\nx + 3"))
    assert result.status == "ok"
    assert result.return_value == 5
    assert "5" in result.stdout
    namespace = {}
    assert asyncio.run(backend.run_code("value = 9", namespace=namespace)).status == "ok"
    assert namespace["value"] == 9
    assert asyncio.run(backend.run_code("1/0")).error_code == "execution_error"
    with pytest.raises(InvalidArgumentsError):
        asyncio.run(backend.run_code(" "))

    syntax = asyncio.run(backend.run_code("if True print('bad')"))
    assert syntax.error_code == "syntax_error"
    material_hint = asyncio.run(
        backend.run_code("print('Listing \"fluid\" materials')\n# list_materials")
    )
    assert "SOLID" in material_hint.stdout

    backend._solver = SimpleNamespace(
        flaky=lambda: (_ for _ in ()).throw(RuntimeError("server not running"))
    )
    disconnected = asyncio.run(backend.run_code("solver.flaky()"))
    assert disconnected.error_code == "solver_disconnected"
    assert backend.is_connected() is False

    backend._solver = SimpleNamespace(settings=SimpleNamespace())

    assert asyncio.run(backend.validate_code("x = 1")).status == "ok"
    with pytest.raises(InvalidArgumentsError):
        asyncio.run(backend.get_help(" "))
    assert asyncio.run(backend.get_help("missing"))["error"].startswith("unresolvable")

    graphics_leaf = SimpleNamespace(
        child_names=["child"],
        allowed_values=lambda: ["a", "b"],
    )
    backend._solver = SimpleNamespace(
        settings=SimpleNamespace(results=SimpleNamespace(graphics_objects=graphics_leaf))
    )
    help_payload = asyncio.run(backend.get_help("results.graphics_objects"))
    assert help_payload["child_names"] == ["child"]
    assert help_payload["allowed_values"] == ["a", "b"]
    assert "note" in help_payload

    backend._solver = SimpleNamespace(settings=SimpleNamespace())

    quality_text = "Minimum Orthogonal Quality = 2.5e-01\nMaximum Ortho skew = 7.5e-01\nMaximum Aspect Ratio = 1.2e+01"  # noqa: E501
    monkeypatch.setattr(
        backend,
        "run_code",
        lambda _code: asyncio.sleep(0, RunCodeResult(status="ok", stdout=quality_text)),
    )
    quality = asyncio.run(backend.mesh_quality())
    assert quality["min_orthogonal_quality"] == pytest.approx(0.25)
    assert asyncio.run(backend.mesh_quality()) is quality

    backend.invalidate_cache()
    backend._solver = None
    assert asyncio.run(backend.mesh_quality()) == {
        "min_orthogonal_quality": None,
        "max_ortho_skew": None,
        "max_aspect_ratio": None,
    }
    backend._solver = SimpleNamespace(settings=SimpleNamespace())
    monkeypatch.setattr(
        backend, "run_code", lambda _code: asyncio.sleep(0, RunCodeResult(status="error"))
    )
    assert asyncio.run(backend.mesh_quality()) == {
        "min_orthogonal_quality": None,
        "max_ortho_skew": None,
        "max_aspect_ratio": None,
    }

    check_text = "Mesh check succeeded.\nDone."
    monkeypatch.setattr(
        backend,
        "run_code",
        lambda _code: asyncio.sleep(0, RunCodeResult(status="ok", stdout=check_text)),
    )
    assert asyncio.run(backend.mesh_check())["raw"] == check_text
    assert asyncio.run(backend.mesh_check())["raw"] == check_text

    backend.invalidate_cache()
    backend._solver = None
    empty_check = asyncio.run(backend.mesh_check())
    assert empty_check["raw"] == ""
    backend._solver = SimpleNamespace(settings=SimpleNamespace())
    monkeypatch.setattr(
        backend, "run_code", lambda _code: asyncio.sleep(0, RunCodeResult(status="error"))
    )
    assert asyncio.run(backend.mesh_check())["raw"] == ""

    backend._solver = SimpleNamespace(scheme=FakeScheme(values={}))
    assert asyncio.run(backend.mesh_counts()) == {
        "cell_count": None,
        "face_count": None,
        "node_count": None,
    }
    backend._solver = SimpleNamespace(
        scheme=FakeScheme(values={next(iter(FakeScheme().values), "unused"): [10, "20", 0]})
    )
    assert asyncio.run(backend.mesh_counts()) == {
        "cell_count": None,
        "face_count": None,
        "node_count": None,
    }
    backend._solver = SimpleNamespace(scheme=lambda _expr: ["10", "20.0", 30])
    assert asyncio.run(backend.mesh_counts()) == {
        "cell_count": 10,
        "face_count": 20,
        "node_count": 30,
    }
    backend.invalidate_mesh_cache()
    backend._solver = SimpleNamespace(scheme=lambda _expr: [None, "bad", False])
    assert asyncio.run(backend.mesh_counts()) == {
        "cell_count": None,
        "face_count": None,
        "node_count": None,
    }
    backend.invalidate_mesh_cache()
    backend._solver = SimpleNamespace(
        scheme=lambda _expr: (_ for _ in ()).throw(RuntimeError("scheme down"))
    )
    assert asyncio.run(backend.mesh_counts()) == {
        "cell_count": None,
        "face_count": None,
        "node_count": None,
    }
    backend.invalidate_mesh_cache()
    backend._solver = SimpleNamespace()
    assert asyncio.run(backend.mesh_counts()) == {
        "cell_count": None,
        "face_count": None,
        "node_count": None,
    }
    backend.invalidate_mesh_cache()
    backend._solver = None
    assert asyncio.run(backend.mesh_counts()) == {
        "cell_count": None,
        "face_count": None,
        "node_count": None,
    }

    def save_picture(file_name):
        """Save picture.

        Parameters
        ----------
        file_name : Any
            File name to supply to the function.

        Returns
        -------
        None
            The function completes through its side effects.
        """
        with Path(file_name).open("wb") as stream:
            stream.write(b"png")

    backend._solver = SimpleNamespace(
        settings=SimpleNamespace(
            results=SimpleNamespace(
                graphics=SimpleNamespace(picture=SimpleNamespace(save_picture=save_picture))
            )
        )
    )
    shot = asyncio.run(backend.screenshot(view="front"))
    assert shot == {"format": "png", "data": "cG5n", "view": "front"}

    backend._solver = SimpleNamespace(settings=SimpleNamespace())
    with pytest.raises(pyfluent.UpstreamError):
        asyncio.run(backend.screenshot())
    backend._solver = None
    with pytest.raises(NotConnectedError):
        asyncio.run(backend.screenshot())


def test_pyfluent_validate_code_semantic_warnings(monkeypatch):
    """Verify that pyfluent validate code semantic warnings.

    Parameters
    ----------
    monkeypatch : Any
        Pytest fixture used to patch environment variables or dependencies.

    Returns
    -------
    None
        The function completes through its side effects.
    """

    class Hit:
        entry = SimpleNamespace(path="setup.models.energy.enabled")

    class FakeIndex:
        available = True

        def lookup(self, path):
            """Exercise the lookup test helper.

            Parameters
            ----------
            path : Any
                Filesystem path or API path to process.

            Returns
            -------
            None
                The function completes through its side effects.
            """
            return None if path.endswith("wrong") else object()

        def search(self, *_args, **_kwargs):
            """Exercise the search test helper.

            Parameters
            ----------
            _args : Any
                Positional arguments forwarded to the wrapped call.
            _kwargs : Any
                Keyword arguments forwarded to the wrapped call.

            Returns
            -------
            None
                The function completes through its side effects.
            """
            return [Hit()]

    monkeypatch.setattr(
        pyfluent, "get_api_index_for_session", lambda _session: FakeIndex(), raising=False
    )
    monkeypatch.setitem(
        sys.modules,
        "ansys.fluent.mcp.solve.catalog.index",
        SimpleNamespace(get_api_index_for_session=lambda _session: FakeIndex()),
    )

    backend = pyfluent.PyFluentBackend()
    result = asyncio.run(backend.validate_code("solver.settings.setup.models.energy.wrong = True"))
    assert result.status == "ok"
    assert result.warnings == [
        "unknown settings path 'setup.models.energy.wrong'; did you mean: setup.models.energy.enabled"  # noqa: E501
    ]
