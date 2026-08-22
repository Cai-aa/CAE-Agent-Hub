# -*- coding: utf-8 -*-
"""optimizer.py - two-stage sizing/parameter optimization loop for CalculiX.

Minimize mass subject to stress/displacement/natural-frequency constraints by
tuning scalar design variables (shell thickness, beam section, material
E/nu/density, load magnitude). This is sizing/parameter optimization - the
geometry and mesh do not change; only scalar cards are edited in place.

Frequency constraints (``freq_<N>_hz``, e.g. ``freq_1_hz > 300`` - "avoid
resonance") run against a ``*FREQUENCY`` deck: each evaluation is an eigen
solve, and thickness thinning stops where mode N would drop below its floor.
A modal deck reports frequencies only (no stress/displacement), so mixing a
stress constraint into a modal optimization makes every point infeasible by
construction; the run warns about missing metrics instead of failing opaquely.

Two-stage strategy (``strategy="twostage"``):

* Stage 1 - Latin Hypercube coarse sweep: draw ``n_lhs`` samples across the
  variables' bounds, evaluate each (modify -> solve -> read), and keep the
  lightest feasible point. LHS covers the box more evenly than random
  sampling at small counts, which suits minute-scale solves.
* Stage 2 - coordinate-descent refinement: from the Stage-1 best, probe each
  variable toward its lower bound (thinner -> lighter). If the current point
  is infeasible, probe toward the upper bound to recover feasibility. Each
  probe tries a jump-to-bound first, then bisection if the jump violates a
  constraint.

Each step has a physical reading ("thin this section, then re-check stress and
deflection") rather than a black-box gradient.

Units: ``read_results`` returns mass in tonnes (consistent with ``*DENSITY`` in
t/mm^3); this module converts to kg (x1000) for output and comparison.

Convergence: all constraints satisfied AND <1% mass improvement for two
consecutive rounds -> converged. Hitting ``max_solves``/``max_iters`` returns
the best feasible point found so far - not a failure.

Public API: :func:`optimize_structure`.
"""
from __future__ import annotations

import logging
import math
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import inp_parser  # noqa: E402
import solver  # noqa: E402

logger = logging.getLogger("calculix_mcp.optimizer")

# read_results reports mass in tonnes (density in t/mm^3); expose/compare in kg.
_T_TO_KG = 1000.0

_DEFAULT_OBJECTIVE = {"metric": "mass", "direction": "minimize"}
_DEFAULT_CONSTRAINTS = [
    {"metric": "max_stress_vm", "op": "<", "value": 250.0},
    {"metric": "max_disp", "op": "<", "value": 1.5},
]

# Constraint metrics read_results can supply: static quantities plus one
# freq_<N>_hz per eigenmode of a *FREQUENCY deck (e.g. freq_1_hz in Hz).
_STATIC_METRICS = {"mass", "max_stress_vm", "max_disp"}
_FREQ_METRIC = re.compile(r"^freq_(\d+)_hz$")

# Converge once mass improves by less than this for this many consecutive rounds.
_CONV_ROUNDS = 2
_CONV_TOL = 0.01


def _metrics_from_results(res: dict) -> dict[str, float | None]:
    """Normalize a ``read_results`` dict to kg / MPa / mm / Hz."""
    mass_t = res.get("mass")
    metrics: dict[str, float | None] = {
        "mass": (mass_t * _T_TO_KG) if mass_t is not None else None,
        "max_stress_vm": res.get("max_stress_vm"),
        "max_disp": res.get("max_disp"),
    }
    for row in res.get("frequencies") or []:
        mode = row.get("mode")
        hz = row.get("freq_hz")
        if mode is not None and hz is not None:
            metrics[f"freq_{int(mode)}_hz"] = float(hz)
    return metrics


def _satisfies(value: float, op: str, limit: float) -> bool:
    if op == "<":
        return value < limit
    if op == "<=":
        return value <= limit
    if op == ">":
        return value > limit
    if op == ">=":
        return value >= limit
    raise ValueError(f"unsupported constraint op: {op!r}")


def _check_feasible(metrics: dict, constraints: list[dict]) -> bool:
    """All constraints satisfied; any missing metric counts as infeasible."""
    for c in constraints:
        v = metrics.get(c["metric"])
        if v is None:
            return False
        if not _satisfies(v, c["op"], c["value"]):
            return False
    return True


def _violation_distance(metrics: dict, constraints: list[dict]) -> float:
    """Dimensionless total constraint violation (0 when fully feasible).

    Each constraint's excess over its limit is divided by the limit magnitude
    so different metrics are comparable. Used to pick the closest-to-feasible
    point as a fallback when nothing is fully feasible.
    """
    total = 0.0
    for c in constraints:
        v = metrics.get(c["metric"])
        if v is None:
            return math.inf
        limit = c["value"]
        scale = max(abs(limit), 1e-9)
        if c["op"] in ("<", "<="):
            excess = v - limit
        else:
            excess = limit - v
        if excess > 0:
            total += excess / scale
    return total


def _latin_hypercube(n_samples: int, n_dims: int, rng: np.random.Generator) -> np.ndarray:
    """Draw ``n_samples`` LHS points in ``[0, 1]^n_dims``.

    Each dimension is split into ``n_samples`` equal strata, one uniform point
    is placed per stratum, and each dimension is independently permuted - so
    every dimension has a uniform marginal and the dimensions are decorrelated.
    Returns shape ``(n_samples, n_dims)``.
    """
    cut = np.linspace(0.0, 1.0, n_samples + 1)
    out = np.empty((n_samples, n_dims))
    for d in range(n_dims):
        lo = cut[:-1]
        hi = cut[1:]
        u = rng.uniform(size=n_samples)
        pts = lo + u * (hi - lo)
        out[:, d] = rng.permutation(pts)
    return out


def _scale_to_bounds(unit_samples: np.ndarray, bounds: list[tuple[float, float]]) -> np.ndarray:
    """Map ``[0, 1]`` samples onto each dimension's ``[lower, upper]``."""
    arr = np.asarray(bounds, dtype=float)
    lo = arr[:, 0]
    hi = arr[:, 1]
    return unit_samples * (hi - lo) + lo


def _evaluate(
    template_inp: Path,
    var_values: dict[str, float],
    work_dir: Path,
    tag: str,
    timeout: int = 1800,
) -> dict[str, Any]:
    """Run one modify -> solve -> read evaluation for a set of variable values.

    Copies the template to ``work_dir/<tag>.inp`` and edits each variable in
    place, then runs ccx and reads the ``.dat``. Returns normalized metrics and
    solver status. On solver failure the metrics are null and ``solver_status``
    is ``"error"``.
    """
    out_inp = work_dir / f"{tag}.inp"
    shutil.copy(str(template_inp), str(out_inp))
    for var_id, val in var_values.items():
        inp_parser.modify_card(str(out_inp), var_id, val, out_path=str(out_inp))

    solve = solver.run_solver(str(out_inp), timeout=timeout)
    if solve["status"] != "ok":
        return {
            "metrics": {"mass": None, "max_stress_vm": None, "max_disp": None},
            "solver_status": "error",
            "dat_path": "",
            "elapsed": solve.get("elapsed", 0.0),
            "error": "; ".join(solve.get("errors") or []) or solve.get("stdout_tail", "")[-300:],
            "inp_path": str(out_inp),
        }
    result_path = solve.get("dat_path") or ""
    res = solver.read_results(result_path)
    metrics = _metrics_from_results(res)
    return {
        "metrics": metrics,
        "solver_status": res.get("status", "ok"),
        "dat_path": res.get("dat_path", ""),
        "elapsed": solve.get("elapsed", 0.0),
        "error": "",
        "inp_path": str(out_inp),
        "warnings": res.get("warnings", []),
    }


def _history_entry(
    iter_id: int,
    stage: str,
    var_values: dict[str, float],
    eval_result: dict,
    constraints: list[dict],
) -> dict[str, Any]:
    """Collect an evaluation into a history record."""
    metrics = eval_result["metrics"]
    return {
        "iter": iter_id,
        "stage": stage,
        "vars": dict(var_values),
        "mass_kg": metrics["mass"],
        "stress_vm": metrics["max_stress_vm"],
        "disp": metrics["max_disp"],
        "freq_1_hz": metrics.get("freq_1_hz"),
        "feasible": (
            _check_feasible(metrics, constraints)
            if eval_result["solver_status"] == "ok"
            else False
        ),
        "solver_status": eval_result["solver_status"],
    }


def _is_better_for_objective(
    candidate_metrics: dict,
    candidate_feasible: bool,
    best_metrics: dict | None,
    best_feasible: bool,
    best_violation: float,
    objective: dict,
    constraints: list[dict],
) -> bool:
    """Whether a candidate beats the current best (minimize mass).

    Priority: feasible beats infeasible; among equal feasibility the lighter
    point wins; if both infeasible, the smaller constraint violation wins.
    """
    if candidate_metrics.get("mass") is None:
        return False
    direction = objective.get("direction", "minimize")
    sign = 1.0 if direction == "minimize" else -1.0
    cand_val = sign * candidate_metrics["mass"]

    if best_metrics is None:
        return True

    if candidate_feasible and not best_feasible:
        return True
    if not candidate_feasible and best_feasible:
        return False
    if candidate_feasible and best_feasible:
        return cand_val < (sign * best_metrics["mass"]) - 1e-12
    cand_viol = _violation_distance(candidate_metrics, constraints)
    return cand_viol < best_violation - 1e-12


def _coord_step(
    template: Path,
    current_vals: dict[str, float],
    vid: str,
    vbounds: list[float],
    current_feasible: bool,
    wdir: Path,
    iter_base: int,
    timeout: int,
    constraints: list[dict],
    max_probes: int = 4,
) -> tuple[dict, dict, dict, int] | None:
    """One coordinate-descent probe on a single variable (jump-to-bound, then bisect).

    For minimize-mass: if the current point is feasible, probe toward the lower
    bound (thinner -> lighter); if infeasible, probe toward the upper bound to
    recover feasibility. Try the bound directly first; if that is rejected,
    bisect the remaining interval up to ``max_probes`` times - each rejection
    halves the interval toward the feasible boundary (a single bisection can
    strand the search when the boundary sits near one end, e.g. a resonance
    floor just below the current thickness).

    Returns ``(new_vals, eval_result, history_entry, used_solves)`` or None if
    the variable cannot improve.
    """
    lo, hi = float(vbounds[0]), float(vbounds[1])
    cur = current_vals[vid]
    target = lo if current_feasible else hi
    if abs(target - cur) < 1e-9:
        return None
    span = abs(hi - lo)

    used = 0
    trial_vals = {**current_vals, vid: target}
    ev = _evaluate(template, trial_vals, wdir, f"iter{iter_base + used}_coord_{vid}_full", timeout)
    used += 1
    entry = _history_entry(iter_base + used - 1, "coord", trial_vals, ev, constraints)
    if _accept_step(ev, entry):
        return trial_vals, ev, entry, used

    # Bisect between the current point and the rejected bound; every rejection
    # moves the far endpoint to the rejected midpoint.
    near, far = cur, target
    while used <= max_probes and abs(far - near) > 0.005 * span:
        mid = (near + far) / 2.0
        if abs(mid - near) < 1e-9:
            break
        trial_vals = {**current_vals, vid: mid}
        ev = _evaluate(
            template, trial_vals, wdir, f"iter{iter_base + used}_coord_{vid}_bis{used}", timeout
        )
        used += 1
        entry = _history_entry(iter_base + used - 1, "coord", trial_vals, ev, constraints)
        if _accept_step(ev, entry):
            return trial_vals, ev, entry, used
        far = mid
    return None


def _accept_step(eval_result: dict, entry: dict) -> bool:
    """Whether to accept a coordinate-descent step.

    For variables monotone in mass (shell/beam thickness: thinner -> lighter),
    accepting an otherwise-feasible trial is equivalent to a strict mass
    improvement. A feasible point recovered from an infeasible one is accepted
    even if heavier, since feasibility dominates.

    This shortcut is NOT valid for non-monotone variables (material E, load
    magnitude), which would need an explicit mass comparison against the
    current point. Only shell/beam thickness variables are validated for this.
    """
    return (
        eval_result["solver_status"] == "ok"
        and entry["mass_kg"] is not None
        and entry["feasible"]
    )


def _validate_inputs(
    objective: dict, strategy: str, variables: dict, inp_path: str, constraints: list[dict]
) -> None:
    if strategy != "twostage":
        raise NotImplementedError(
            f"strategy={strategy!r} not implemented (only 'twostage')"
        )
    if objective.get("metric") != "mass" or objective.get("direction") != "minimize":
        raise ValueError(
            f"only objective={{metric:'mass', direction:'minimize'}} supported; got {objective}"
        )
    for c in constraints:
        metric = c.get("metric")
        if metric not in _STATIC_METRICS and not _FREQ_METRIC.match(str(metric)):
            raise ValueError(
                f"unknown constraint metric {metric!r}; valid: mass, max_stress_vm, "
                f"max_disp (static decks) and freq_<N>_hz e.g. freq_1_hz (*FREQUENCY decks)"
            )
    if not variables:
        raise ValueError("variables is empty; pass at least one {var_id: [lower, upper]}")
    for vid, b in variables.items():
        if not isinstance(b, (list, tuple)) or len(b) != 2:
            raise ValueError(f"variables[{vid!r}] must be [lower, upper]; got {b}")
        if float(b[0]) >= float(b[1]):
            raise ValueError(f"variables[{vid!r}] lower {b[0]} >= upper {b[1]}")
    if not Path(inp_path).exists():
        raise FileNotFoundError(f"inp not found: {inp_path}")


def _current_values(inp_path: str, var_ids: list[str]) -> dict[str, float]:
    """Read each variable's current value from the deck (the baseline)."""
    dvars = inp_parser.list_design_vars(inp_path)["variables"]
    by_id = {v["var_id"]: v["current_value"] for v in dvars}
    out: dict[str, float] = {}
    for vid in var_ids:
        if vid not in by_id or by_id[vid] is None:
            raise ValueError(f"variable {vid!r} not found in {inp_path} (check list_design_vars)")
        out[vid] = float(by_id[vid])
    return out


def _persist_best(template: Path, best_entry: dict) -> str:
    """Persist the best design next to the template as ``<stem>.optimized.inp``.

    The best variable set is re-applied to a fresh copy of the template so the
    output does not depend on transient work-directory files.
    """
    dest = template.parent / f"{template.stem}.optimized.inp"
    shutil.copy(str(template), str(dest))
    for vid, val in best_entry["vars"].items():
        inp_parser.modify_card(str(dest), vid, val, out_path=str(dest))
    return str(dest)


def _is_bound_limited(
    best_vars: dict[str, float], variables: dict[str, list[float]], tol: float = 1e-6
) -> bool:
    """True when every best variable sits at its lower or upper bound.

    Distinguishes 'budget ran out but the box optimum was found' (the user
    needs to widen bounds to do better) from 'budget ran out with room left'.
    """
    if not best_vars or not variables:
        return False
    for vid, val in best_vars.items():
        bounds = variables.get(vid)
        if not bounds or len(bounds) != 2:
            return False
        lo, hi = float(bounds[0]), float(bounds[1])
        at_lo = abs(val - lo) <= tol * max(1.0, abs(lo))
        at_hi = abs(val - hi) <= tol * max(1.0, abs(hi))
        if not (at_lo or at_hi):
            return False
    return True


def _assemble_result(
    status: str,
    strategy: str,
    converged: bool,
    convergence_reason: str,
    termination_reason: str,
    bound_limited: bool,
    n_solves: int,
    baseline: dict,
    best: dict,
    best_inp_dest: str,
    history: list[dict],
    objective: dict,
    constraints: list[dict],
    variables: dict,
    warnings: list[str],
) -> dict:
    base_mass = baseline.get("mass_kg")
    best_mass = best.get("mass_kg")
    reduction_pct = None
    if base_mass is not None and best_mass is not None and base_mass > 0:
        reduction_pct = round((best_mass - base_mass) / base_mass * 100.0, 3)
    for h in history:
        h["is_best"] = (h["iter"] == best["iter"])
    best_summary = {
        "iter": best["iter"],
        "vars": best["vars"],
        "mass_kg": best["mass_kg"],
        "stress_vm": best["stress_vm"],
        "disp": best["disp"],
        "freq_1_hz": best.get("freq_1_hz"),
        "feasible": best["feasible"],
        "inp_path": best_inp_dest,
        "mass_reduction_pct": reduction_pct,
    }
    return {
        "status": status,
        "strategy": strategy,
        "converged": converged,
        "convergence_reason": convergence_reason,
        "termination_reason": termination_reason,
        "bound_limited": bound_limited,
        "n_solves": n_solves,
        "baseline": {
            "iter": baseline["iter"],
            "vars": baseline["vars"],
            "mass_kg": base_mass,
            "stress_vm": baseline["stress_vm"],
            "disp": baseline["disp"],
            "freq_1_hz": baseline.get("freq_1_hz"),
            "feasible": baseline["feasible"],
        },
        "best": best_summary,
        "history": history,
        "objective": objective,
        "constraints": constraints,
        "variables": variables,
        "all_feasible_found": best["feasible"],
        "warnings": warnings,
    }


def optimize_structure(
    inp_path: str,
    variables: dict[str, list[float]],
    objective: dict | None = None,
    constraints: list[dict] | None = None,
    strategy: str = "twostage",
    max_iters: int = 6,
    seed: int = 42,
    n_lhs: int = 5,
    max_solves: int = 10,
    work_dir: str | None = None,
    timeout: int = 1800,
) -> dict:
    """Run two-stage sizing optimization on a CalculiX ``.inp`` (min mass s.t. constraints).

    Args:
        inp_path: template ``.inp`` (never modified; the best design is saved
            separately as ``<stem>.optimized.inp``).
        variables: ``{var_id: [lower, upper]}``, where var_id comes from
            ``list_design_vars`` (e.g. ``{"shell.UPPER.thickness": [4.5, 6.2]}``).
        objective: ``{"metric": "mass", "direction": "minimize"}`` (the default).
            Only mass/minimize is supported in this version.
        constraints: ``[{metric, op, value}, ...]`` (default
            ``max_stress_vm < 250 MPa`` and ``max_disp < 1.5 mm``). Static
            metrics (``max_stress_vm``, ``max_disp``) need a ``*STATIC`` deck;
            ``freq_<N>_hz`` (e.g. ``{"metric": "freq_1_hz", "op": ">",
            "value": 300.0}`` - avoid resonance) needs a ``*FREQUENCY`` deck,
            with mode N read from the ``.dat`` eigenvalue table.
        strategy: only ``"twostage"``.
        max_iters: max coordinate-descent rounds in Stage 2.
        seed: LHS seed (reproducible).
        n_lhs: number of Latin Hypercube samples in Stage 1.
        max_solves: total solve budget (baseline + LHS + coord descent).
        work_dir: working directory (None -> a temp dir, cleaned up afterward).
        timeout: per-solve timeout in seconds.

    Returns:
        ``{status, strategy, converged, convergence_reason, termination_reason,
        bound_limited, n_solves, baseline, best, history, objective,
        constraints, variables, warnings}``.

        Termination semantics:

        * ``converged=True`` with ``termination_reason`` ``"local_optimum"``
          (no variable improved in a round) or ``"improvement_stall"`` (<1%
          mass improvement for two consecutive rounds).
        * ``converged=False`` with ``"budget_exhausted"`` (``max_solves`` hit)
          or ``"max_iters"`` (rounds exhausted). This is not a failure:
          ``best`` is still the best feasible point found; ``bound_limited``
          tells whether it already sits at the box optimum.
    """
    obj = objective or dict(_DEFAULT_OBJECTIVE)
    cons = constraints if constraints is not None else [dict(c) for c in _DEFAULT_CONSTRAINTS]

    _validate_inputs(obj, strategy, variables, inp_path, cons)

    template = Path(inp_path).resolve()
    rng = np.random.default_rng(seed)
    var_ids = list(variables.keys())
    bounds = [tuple(variables[v]) for v in var_ids]
    base_vals = _current_values(str(template), var_ids)

    own_tmp = work_dir is None
    wdir = Path(work_dir).resolve() if work_dir else Path(tempfile.mkdtemp(prefix="cx_opt_"))
    wdir.mkdir(parents=True, exist_ok=True)
    warnings: list[str] = []
    history: list[dict] = []
    n_solves = 0
    iter_id = 0

    try:
        baseline_eval = _evaluate(template, base_vals, wdir, "iter0_baseline", timeout)
        n_solves += 1
        baseline_entry = _history_entry(iter_id, "baseline", base_vals, baseline_eval, cons)
        history.append(baseline_entry)
        if baseline_eval["solver_status"] != "ok":
            warnings.append(
                f"baseline solve failed (status={baseline_eval['solver_status']}); "
                f"optimization proceeds against LHS samples"
            )
        else:
            missing = [
                c["metric"] for c in cons
                if baseline_eval["metrics"].get(c["metric"]) is None
            ]
            if missing:
                warnings.append(
                    f"baseline reports no result for constraint metric(s) {missing}; a "
                    f"*FREQUENCY deck yields freq_<N>_hz only, a static deck yields "
                    f"stress/displacement only - check the constraint set matches the deck"
                )

        best_entry = baseline_entry
        best_metrics = baseline_eval["metrics"]
        best_violation = (
            _violation_distance(best_metrics, cons)
            if best_entry["solver_status"] == "ok"
            else math.inf
        )

        # Stage 1 - Latin Hypercube coarse sweep.
        unit = _latin_hypercube(n_lhs, len(var_ids), rng)
        scaled = _scale_to_bounds(unit, bounds)
        for s_idx in range(n_lhs):
            if n_solves >= max_solves:
                warnings.append(f"max_solves={max_solves} reached during Stage 1 LHS")
                break
            sample_vals = {var_ids[d]: float(scaled[s_idx, d]) for d in range(len(var_ids))}
            iter_id += 1
            ev = _evaluate(template, sample_vals, wdir, f"iter{iter_id}_lhs{s_idx}", timeout)
            n_solves += 1
            entry = _history_entry(iter_id, "lhs", sample_vals, ev, cons)
            history.append(entry)
            if ev["solver_status"] != "ok":
                warnings.append(f"LHS sample {s_idx} solve failed: {ev.get('error', '')[:120]}")
                continue
            if _is_better_for_objective(
                ev["metrics"], entry["feasible"], best_metrics,
                best_entry["feasible"], best_violation, obj, cons,
            ):
                best_entry = entry
                best_metrics = ev["metrics"]
                best_violation = _violation_distance(best_metrics, cons)

        # Stage 2 - coordinate-descent refinement from the Stage-1 best.
        converged = False
        convergence_reason = ""
        termination_reason = ""
        rounds_without_improve = 0
        current_vals = dict(best_entry["vars"])
        current_feasible = best_entry["feasible"]
        current_metrics = best_metrics

        for round_idx in range(max_iters):
            if n_solves >= max_solves:
                convergence_reason = f"max_solves={max_solves} reached"
                termination_reason = "budget_exhausted"
                break
            improved_this_round = False
            round_start_mass = current_metrics.get("mass")
            for vid in var_ids:
                if n_solves >= max_solves:
                    break
                step_result = _coord_step(
                    template, current_vals, vid, variables[vid], current_feasible,
                    wdir, iter_id + 1, timeout, cons,
                )
                if step_result is None:
                    continue
                new_vals, new_eval, new_entry, used_iters = step_result
                n_solves += used_iters
                iter_id += used_iters
                history.append(new_entry)
                current_vals = dict(new_vals)
                current_metrics = new_eval["metrics"]
                current_feasible = new_entry["feasible"]
                improved_this_round = True
                if new_entry["feasible"] and _is_better_for_objective(
                    new_eval["metrics"], new_entry["feasible"], best_metrics,
                    best_entry["feasible"], best_violation, obj, cons,
                ):
                    best_entry = new_entry
                    best_metrics = new_eval["metrics"]
                    best_violation = _violation_distance(best_metrics, cons)
            if not improved_this_round:
                converged = True
                convergence_reason = f"coordinate-descent local optimum (round {round_idx + 1})"
                termination_reason = "local_optimum"
                break
            if round_start_mass is not None and current_metrics.get("mass") is not None:
                rel = abs(current_metrics["mass"] - round_start_mass) / max(abs(round_start_mass), 1e-9)
                rounds_without_improve = rounds_without_improve + 1 if rel < _CONV_TOL else 0
                if rounds_without_improve >= _CONV_ROUNDS:
                    converged = True
                    convergence_reason = (
                        f"mass improvement < {_CONV_TOL * 100:.0f}% for {_CONV_ROUNDS} consecutive rounds"
                    )
                    termination_reason = "improvement_stall"
                    break
        else:
            if not termination_reason:
                convergence_reason = f"max_iters={max_iters} reached"
                termination_reason = "max_iters"

        if not termination_reason:
            convergence_reason = "max_iters reached"
            termination_reason = "max_iters"

        bound_limited = _is_bound_limited(best_entry.get("vars", {}), variables)
        best_inp_dest = _persist_best(template, best_entry)

        return _assemble_result(
            status="ok",
            strategy=strategy,
            converged=converged,
            convergence_reason=convergence_reason,
            termination_reason=termination_reason,
            bound_limited=bound_limited,
            n_solves=n_solves,
            baseline=baseline_entry,
            best=best_entry,
            best_inp_dest=best_inp_dest,
            history=history,
            objective=obj,
            constraints=cons,
            variables=variables,
            warnings=warnings,
        )
    finally:
        if own_tmp:
            shutil.rmtree(wdir, ignore_errors=True)


__all__ = ["optimize_structure"]
