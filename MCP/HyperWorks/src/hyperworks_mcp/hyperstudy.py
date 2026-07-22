from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

from .projects import ProjectService
from .settings import safe_filename, within


VARNAME_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,63}\Z")
EXPRESSION_RE = re.compile(r"[A-Za-z0-9_+\-*/().,\s]{1,500}\Z")
DOE_DESIGNS = {"Hammersley", "FullFactorial", "ModifiedExtensibleLatticeSequence"}
OPTIMIZATION_DESIGNS = {"GRSM"}


def _label(value: Any, name: str) -> str:
    text = str(value).strip()
    if not text or len(text) > 128:
        raise ValueError(f"{name} must contain between 1 and 128 characters")
    return text


def _varname(value: Any, name: str) -> str:
    text = str(value).strip()
    if not VARNAME_RE.fullmatch(text):
        raise ValueError(f"{name} must be an identifier of at most 64 characters")
    return text


def _finite(value: Any, name: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric") from exc
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    return result


def _clean_variables(values: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(values, list) or not 1 <= len(values) <= 100:
        raise ValueError("variables must contain between 1 and 100 items")
    result = []
    names = set()
    for index, item in enumerate(values):
        if not isinstance(item, dict):
            raise ValueError(f"variables[{index}] must be an object")
        varname = _varname(item.get("varname", ""), f"variables[{index}].varname")
        if varname in names:
            raise ValueError(f"Duplicate variable varname: {varname}")
        names.add(varname)
        lower = _finite(item.get("lower"), f"variables[{index}].lower")
        nominal = _finite(item.get("nominal"), f"variables[{index}].nominal")
        upper = _finite(item.get("upper"), f"variables[{index}].upper")
        if not lower <= nominal <= upper or lower == upper:
            raise ValueError(
                f"variables[{index}] must satisfy lower <= nominal <= upper and lower < upper"
            )
        result.append(
            {
                "label": _label(item.get("label", varname), f"variables[{index}].label"),
                "varname": varname,
                "lower": lower,
                "nominal": nominal,
                "upper": upper,
            }
        )
    return result


def _clean_responses(values: list[dict[str, Any]], variables: set[str]) -> list[dict[str, Any]]:
    if not isinstance(values, list) or not 1 <= len(values) <= 100:
        raise ValueError("responses must contain between 1 and 100 items")
    result = []
    names = set()
    for index, item in enumerate(values):
        if not isinstance(item, dict):
            raise ValueError(f"responses[{index}] must be an object")
        varname = _varname(item.get("varname", ""), f"responses[{index}].varname")
        if varname in names or varname in variables:
            raise ValueError(f"Duplicate or conflicting response varname: {varname}")
        names.add(varname)
        expression = str(item.get("expression", "")).strip()
        if not EXPRESSION_RE.fullmatch(expression):
            raise ValueError(
                f"responses[{index}].expression contains unsupported characters"
            )
        result.append(
            {
                "label": _label(item.get("label", varname), f"responses[{index}].label"),
                "varname": varname,
                "expression": expression,
            }
        )
    return result


def _clean_doe(value: dict[str, Any] | None) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("doe must be an object")
    design = str(value.get("design", "Hammersley"))
    if design not in DOE_DESIGNS:
        raise ValueError("Unsupported DOE design: " + design)
    runs = int(value.get("runs", 20))
    if not 2 <= runs <= 100000:
        raise ValueError("doe.runs must be between 2 and 100000")
    return {
        "label": _label(value.get("label", "DOE"), "doe.label"),
        "design": design,
        "runs": runs,
    }


def _clean_optimization(
    value: dict[str, Any] | None, responses: set[str]
) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("optimization must be an object")
    design = str(value.get("design", "GRSM"))
    if design not in OPTIMIZATION_DESIGNS:
        raise ValueError("Unsupported optimization design: " + design)
    goals = value.get("goals")
    if not isinstance(goals, list) or not 1 <= len(goals) <= 100:
        raise ValueError("optimization.goals must contain between 1 and 100 items")
    clean_goals = []
    names = set()
    for index, item in enumerate(goals):
        if not isinstance(item, dict):
            raise ValueError(f"optimization.goals[{index}] must be an object")
        varname = _varname(
            item.get("varname", ""), f"optimization.goals[{index}].varname"
        )
        if varname in names:
            raise ValueError(f"Duplicate optimization goal varname: {varname}")
        names.add(varname)
        response = _varname(
            item.get("response", ""), f"optimization.goals[{index}].response"
        )
        if response not in responses:
            raise ValueError(f"Unknown optimization response: {response}")
        kind = str(item.get("type", "Minimize"))
        if kind not in {"Minimize", "Maximize", "Constraint"}:
            raise ValueError(f"Unsupported optimization goal type: {kind}")
        clean = {
            "label": _label(
                item.get("label", varname), f"optimization.goals[{index}].label"
            ),
            "varname": varname,
            "response": response,
            "type": kind,
        }
        if kind == "Constraint":
            bound_type = str(item.get("bound_type", "<="))
            if bound_type not in {"<=", ">="}:
                raise ValueError("Constraint bound_type must be <= or >=")
            clean["bound_type"] = bound_type
            clean["bound_value"] = _finite(
                item.get("bound_value"), f"optimization.goals[{index}].bound_value"
            )
        clean_goals.append(clean)
    max_evaluations = int(value.get("max_evaluations", 50))
    if not 1 <= max_evaluations <= 100000:
        raise ValueError("optimization.max_evaluations must be between 1 and 100000")
    return {
        "label": _label(value.get("label", "Optimization"), "optimization.label"),
        "design": design,
        "max_evaluations": max_evaluations,
        "goals": clean_goals,
    }


def normalize_math_study_spec(
    study_name: str,
    variables: list[dict[str, Any]],
    responses: list[dict[str, Any]],
    doe: dict[str, Any] | None = None,
    optimization: dict[str, Any] | None = None,
) -> dict[str, Any]:
    name = _label(study_name, "study_name")
    clean_variables = _clean_variables(variables)
    variable_names = {item["varname"] for item in clean_variables}
    clean_responses = _clean_responses(responses, variable_names)
    response_names = {item["varname"] for item in clean_responses}
    return {
        "study_name": name,
        "variables": clean_variables,
        "responses": clean_responses,
        "doe": _clean_doe(doe),
        "optimization": _clean_optimization(optimization, response_names),
    }


def render_math_study_script(spec: dict[str, Any], study_directory: Path) -> str:
    payload = json.dumps(spec, ensure_ascii=False, separators=(",", ":"))
    directory = study_directory.as_posix()
    return f'''from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import alt.hst.api.hstapp as hstapp
import alt.hst.api.session as sess
from alt.hst.api import api_objects


SPEC = json.loads({payload!r})
STUDY_DIR = Path({directory!r})


def build_study():
    STUDY_DIR.mkdir(parents=True, exist_ok=True)
    study_list = sess.getStudyList()
    study = study_list.add()
    study.setDirectory(str(STUDY_DIR))
    study.setFolder(str(STUDY_DIR))
    study.setStudyFile(str(STUDY_DIR / "Study_1.hstudy"))
    study.setVarname("mcp_study")
    study.setLabel(SPEC["study_name"])

    setup = study.getApproachList()[0]
    model = setup.getDefinition().getModelList().add()
    model.setModelToolType(api_objects.ModelToolTypes.TYPE_HST_INTERNAL_MATH)

    variable_list = setup.getDefinition().getDesignVariableList()
    for item in SPEC["variables"]:
        variable = variable_list.add()
        variable.setDataType(api_objects.DataType.REAL)
        variable.setLabel(item["label"])
        variable.setVarname(item["varname"])
        variable.setLowerBound(item["lower"])
        variable.setNominalValue(item["nominal"])
        variable.setUpperBound(item["upper"])
        variable.setFormatToolType(api_objects.FormatToolTypes.TYPE_CONTINUOUS)

    response_list = setup.getDefinition().getResponseList()
    for item in SPEC["responses"]:
        response = response_list.add()
        response.setLabel(item["label"])
        response.setVarname(item["varname"])
        response.setType(api_objects.DataType.REAL)
        response.setEquation(item["expression"])

    if SPEC["doe"]:
        item = SPEC["doe"]
        doe = study.getApproachList().add()
        doe.setApproachToolType(api_objects.ApproachToolTypes.TYPE_DOE)
        doe.setLabel(item["label"])
        tool = cast(api_objects.ApproachTool_Doe, doe.getApproachTool())
        doe.setDesignVarname(item["design"])
        tool.getDesign().setNamedAttribute("NumRuns", item["runs"])
        tool.setUncontrolledPerturbationVarname("Initial")
        doe.applySpecification()

    if SPEC["optimization"]:
        item = SPEC["optimization"]
        optimization = study.getApproachList().add()
        optimization.setApproachToolType(api_objects.ApproachToolTypes.TYPE_OPT)
        optimization.setLabel(item["label"])
        goal_list = optimization.getDefinition().getGoalList()
        for goal_item in item["goals"]:
            goal = goal_list.add()
            goal.setLabel(goal_item["label"])
            goal.setVarname(goal_item["varname"])
            goal.setResponse(goal_item["response"])
            goal.setType(goal_item["type"])
            if goal_item["type"] == "Constraint":
                goal.setBoundType(goal_item["bound_type"])
                goal.setBoundValue(goal_item["bound_value"])
        tool = cast(api_objects.ApproachTool_Optimization, optimization.getApproachTool())
        optimization.setDesignVarname(item["design"])
        tool.getDesign().setNamedAttribute("MAXDES", item["max_evaluations"])
        optimization.applySpecification()

    study.save()
    result = {{"study_file": study.getStudyFile(), "study_varname": study.getVarname()}}
    study_list.closeStudy(study.getVarname())
    print("__HYPERWORKS_MCP_HYPERSTUDY_READY__=" + json.dumps(result))


with hstapp.HstBatchApp():
    build_study()
'''


class HyperStudyService:
    def __init__(self, projects: ProjectService):
        self.projects = projects

    def prepare_math_study(
        self,
        project_id: str,
        study_name: str,
        variables: list[dict[str, Any]],
        responses: list[dict[str, Any]],
        doe: dict[str, Any] | None = None,
        optimization: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        spec = normalize_math_study_spec(
            study_name, variables, responses, doe, optimization
        )
        root = self.projects.root(project_id)
        slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", study_name).strip("._")[:48]
        slug = slug or "study"
        study_directory = within(root / "output" / ("hyperstudy_" + slug), root)
        script_name = safe_filename("__mcp_hst_" + slug + ".py", ".py")
        script_path = within(root / "scripts" / script_name, root)
        spec_path = within(root / "scripts" / ("__mcp_hst_" + slug + ".json"), root)
        if script_path.exists() or spec_path.exists() or study_directory.exists():
            raise ValueError(
                "A HyperStudy artifact with this study_name already exists in the project"
            )
        script_path.write_text(
            render_math_study_script(spec, study_directory), encoding="utf-8"
        )
        spec_path.write_text(
            json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return {
            "project_id": project_id,
            "study_name": spec["study_name"],
            "script_name": script_name,
            "script_file": str(script_path),
            "spec_file": str(spec_path),
            "study_directory": str(study_directory),
            "expected_study_file": str(study_directory / "Study_1.hstudy"),
            "variable_count": len(spec["variables"]),
            "response_count": len(spec["responses"]),
            "has_doe": spec["doe"] is not None,
            "has_optimization": spec["optimization"] is not None,
        }

    def generated_script(self, project_id: str, script_name: str) -> Path:
        filename = safe_filename(script_name, ".py")
        if not filename.startswith("__mcp_hst_"):
            raise ValueError("Only MCP-generated HyperStudy scripts may be executed")
        root = self.projects.root(project_id)
        path = within(root / "scripts" / filename, root)
        if not path.is_file():
            raise ValueError(f"Generated HyperStudy script not found: {filename}")
        return path
