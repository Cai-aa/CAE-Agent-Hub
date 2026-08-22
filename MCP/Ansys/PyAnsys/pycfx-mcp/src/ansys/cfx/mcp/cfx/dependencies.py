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

"""Prerequisite checks for deterministic CFX code generation."""

from __future__ import annotations

from typing import Any

_PRE_RECIPE_PREFIXES = (
    "cfx_single_phase_steady",
    "cfx_set_boundary_conditions",
    "cfx_domain_physics",
    "cfx_convergence_monitors",
)
_SOLVER_RECIPE_PREFIXES = (
    "cfx_run_solver_steady",
    "cfx_solver_",
)
_POST_RECIPE_PREFIXES = ("cfx_post_",)


def _text_blob(*values: str | None) -> str:
    """Combine prerequisite inputs into lowercase text for intent matching.

    Parameters
    ----------
    values : str | None
        Candidate values to combine or inspect.

    Returns
    -------
    str
        String value produced for the requested CFX or provider operation.
    """
    return " ".join(value or "" for value in values).lower()


def _has_value(mapping: dict[str, Any], *keys: str) -> bool:
    """Return whether any of the requested keys has a usable value.

    Parameters
    ----------
    mapping : dict[str, Any]
        Mapping that contains candidate prerequisite or context values.
    keys : str
        Keys to read from the mapping.

    Returns
    -------
    bool
        Boolean answer for the requested condition.
    """
    return any(bool(mapping.get(key)) for key in keys)


def _needs_pre(intent: str, recipe_name: str | None) -> bool:
    """Return whether the request needs an active CFX-Pre session.

    Parameters
    ----------
    intent : str
        User request text for inferring the required CFX action.
    recipe_name : str | None
        Name of the matched CFX recipe, when one is available.

    Returns
    -------
    bool
        Boolean answer for the requested condition.
    """
    if recipe_name and recipe_name.startswith(_PRE_RECIPE_PREFIXES):
        return True
    tokens = _text_blob(intent)
    return any(
        token in tokens
        for token in (
            "cfx-pre",
            "preprocess",
            "pre-process",
            "boundary",
            "domain",
            "mesh",
            "inlet",
            "outlet",
            "wall",
            "write solver input",
        )
    )


def _needs_solver_def(intent: str, recipe_name: str | None) -> bool:
    """Return whether the request needs a solver input file.

    Parameters
    ----------
    intent : str
        User request text for inferring the required CFX action.
    recipe_name : str | None
        Name of the matched CFX recipe, when one is available.

    Returns
    -------
    bool
        Boolean answer for the requested condition.
    """
    if recipe_name and recipe_name.startswith(_SOLVER_RECIPE_PREFIXES):
        return True
    tokens = _text_blob(intent)
    return "solver" in tokens and any(
        token in tokens for token in ("run", "start", "launch", "wait", "progress")
    )


def _needs_post(intent: str, recipe_name: str | None) -> bool:
    """Return whether the request needs an active CFD-Post session.

    Parameters
    ----------
    intent : str
        User request text for inferring the required CFX action.
    recipe_name : str | None
        Name of the matched CFX recipe, when one is available.

    Returns
    -------
    bool
        Boolean answer for the requested condition.
    """
    if recipe_name and recipe_name.startswith(_POST_RECIPE_PREFIXES):
        return True
    tokens = _text_blob(intent)
    return any(
        token in tokens
        for token in (
            "cfd-post",
            "postprocess",
            "post-process",
            "postprocessing",
            "contour",
            "plot",
            "hardcopy",
            "picture",
            "plane",
            "results file",
        )
    )


def _start_pre_clarification() -> dict[str, Any]:
    """Create a clarification asking how CFX-Pre should be started.

    Returns
    -------
    dict[str, Any]
        Structured response payload for the requested operation.
    """
    return {
        "id": "start_cfx_pre",
        "message": "A CFX-Pre session is required before generating this setup code.",
        "question": "How should I handle the missing CFX-Pre session?",
        "options": [
            {
                "label": "Start CFX-Pre now",
                "value": "start_pre_now",
                "description": "Launch a local CFX-Pre session before continuing.",
            },
            {
                "label": "Include launch code",
                "value": "include_pre_launch_code",
                "description": "Generate code that starts CFX-Pre as part of the script.",
            },
            {
                "label": "Assume CFX-Pre exists",
                "value": "assume_pre",
                "description": "Generate code assuming a session variable is already available.",
            },
            {
                "label": "Cancel",
                "value": "cancel",
                "description": "Stop instead of generating speculative CFX setup code.",
            },
        ],
    }


def _def_file_clarification() -> dict[str, Any]:
    """Create a clarification asking for the solver input file to use.

    Returns
    -------
    dict[str, Any]
        Structured response payload for the requested operation.
    """
    return {
        "id": "provide_cfx_def_file",
        "message": "A CFX solver input .def file is required before launching the solver.",
        "question": "Which CFX solver input file should be used?",
        "options": [
            {
                "label": "Provide .def path",
                "value": "provide_def_file",
                "description": "Use a specific solver input file path.",
            },
            {
                "label": "Use current context",
                "value": "use_context_def_file",
                "description": "Continue if the request context already includes a def_file.",
            },
            {
                "label": "Cancel",
                "value": "cancel",
                "description": "Stop until a solver input file is available.",
            },
        ],
    }


def _start_post_clarification() -> dict[str, Any]:
    """Create a clarification asking how CFD-Post should be started.

    Returns
    -------
    dict[str, Any]
        Structured response payload for the requested operation.
    """
    return {
        "id": "start_cfx_post",
        "message": "A CFD-Post session and CFX results file are required for postprocessing.",
        "question": "How should I handle the missing CFD-Post context?",
        "options": [
            {
                "label": "Start CFD-Post",
                "value": "start_post",
                "description": "Launch CFD-Post with a provided results file.",
            },
            {
                "label": "Provide .res path",
                "value": "provide_res_file",
                "description": "Use an existing CFX results file.",
            },
            {
                "label": "Assume CFD-Post exists",
                "value": "assume_post",
                "description": "Generate code assuming a postprocessing session is already available.",  # noqa: E501
            },
            {
                "label": "Cancel",
                "value": "cancel",
                "description": "Stop until postprocessing inputs are available.",
            },
        ],
    }


def check_cfx_prerequisites(
    *,
    intent: str | None = None,
    recipe_name: str | None = None,
    params: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
    status: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Check CFX-specific prerequisites for an intent, recipe, and connection state.

    Parameters
    ----------
    intent : str | None, default: None
        User request text used to infer the required CFX action.
    recipe_name : str | None, default: None
        Name of the matched CFX recipe, when one is available.
    params : dict[str, Any] | None, default: None
        Action-specific parameter mapping.
    context : dict[str, Any] | None, default: None
        Additional context supplied by the caller.
    status : dict[str, Any] | None, default: None
        Current connection status used to decide whether prerequisites are satisfied.

    Returns
    -------
    dict[str, Any]
        Structured response payload for the requested operation.
    """
    params = params or {}
    context = context or {}
    status = status or {}
    intent_text = intent or ""

    missing_ids: list[str] = []
    clarifications: list[dict[str, Any]] = []

    pre_connected = bool(status.get("pre") or status.get("cfx_pre"))
    post_connected = bool(status.get("post") or status.get("cfx_post"))

    if _needs_pre(intent_text, recipe_name) and not pre_connected:
        missing_ids.append("session:cfx_pre")
        clarifications.append(_start_pre_clarification())

    has_def_file = (
        _has_value(params, "def_file", "solver_input_file", "solver_input_file_name")
        or _has_value(context, "def_file", "solver_input_file", "solver_input_file_name")
        or _has_value(status, "def_file", "solver_input_file", "solver_input_file_name")
    )
    if _needs_solver_def(intent_text, recipe_name) and not has_def_file:
        missing_ids.append("artifact:def_file")
        clarifications.append(_def_file_clarification())

    has_res_file = (
        _has_value(params, "res_file", "results_file", "results_file_name")
        or _has_value(context, "res_file", "results_file", "results_file_name")
        or _has_value(status, "res_file", "results_file", "results_file_name")
    )
    if _needs_post(intent_text, recipe_name):
        if not has_res_file:
            missing_ids.append("artifact:res_file")
        if not post_connected:
            missing_ids.append("session:cfx_post")
        if not has_res_file or not post_connected:
            clarifications.append(_start_post_clarification())

    return {
        "ready": not missing_ids,
        "missing_ids": missing_ids,
        "clarifications": clarifications,
    }


def primary_clarification(check: dict[str, Any]) -> dict[str, Any] | None:
    """Return the first clarification that should be shown to the user.

    Parameters
    ----------
    check : dict[str, Any]
        Prerequisite-check result to convert into a user-facing clarification.

    Returns
    -------
    dict[str, Any] | None
        Value computed by the helper for the requested CFX workflow.
    """
    clarifications = check.get("clarifications")
    if isinstance(clarifications, list) and clarifications:
        first = clarifications[0]
        if isinstance(first, dict):
            return first
    return None
