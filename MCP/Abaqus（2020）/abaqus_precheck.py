# -*- coding: utf-8 -*-
"""
Abaqus Model Pre-Validation Module
==================================

Provides pre-submission validation for Abaqus models to catch common
completeness issues before submitting a job. Python 2.7 compatible.

This module is designed to run inside Abaqus/CAE (Python 2.7) but can also
be imported outside of Abaqus for linting or unit testing because all
Abaqus imports are wrapped in try/except.

Usage inside Abaqus::

    from abaqus_precheck import validate_model, validate_and_report
    model = mdb.models['Model-1']
    result = validate_model(model, job_name='Job-1')
    if not result['valid']:
        for err in result['errors']:
            print('ERROR:', err)

    # Or print a formatted report:
    validate_and_report(model, job_name='Job-1')
"""
from __future__ import print_function

import sys

# Detect Python version (Abaqus 2020 ships with Python 2.7)
PY2 = sys.version_info[0] == 2

# ---------------------------------------------------------------------------
# Abaqus imports -- wrapped in try/except so this module can be imported
# outside of Abaqus (e.g. for linting or unit testing) without crashing.
# Only ``mdb`` is needed for the optional job-existence check; the ``model``
# object itself is always passed in by the caller.
# ---------------------------------------------------------------------------
try:
    from abaqus import mdb  # noqa: F401
    ABAQUS_AVAILABLE = True
except Exception:
    mdb = None
    ABAQUS_AVAILABLE = False


__all__ = [
    "validate_model",
    "validate_and_report",
    "ABAQUS_AVAILABLE",
]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _safe_str(value):
    """Convert a value to a safe string.

    On Chinese Windows + Python 2.7, Abaqus may produce GBK-encoded ``str``
    (bytes) from exception messages.  This helper decodes such bytes to
    ``unicode`` so that the resulting error strings survive JSON
    serialisation with ``ensure_ascii=True``.
    """
    if PY2 and isinstance(value, str):
        try:
            return value.decode("utf-8")
        except (UnicodeDecodeError, UnicodeEncodeError):
            try:
                return value.decode("gbk")
            except (UnicodeDecodeError, UnicodeEncodeError):
                return value.decode("latin-1", errors="replace")
    return str(value)


def _repo_keys(repository):
    """Return a list of keys from a Repository-like object.

    Abaqus ``Repository`` objects must be iterated via ``.keys()``; iterating
    directly raises ``TypeError``.  This helper never raises -- on any error
    it returns an empty list.
    """
    try:
        return list(repository.keys())
    except Exception:
        return []


def _repo_len(repository):
    """Return the number of items in a Repository-like object (never raises)."""
    try:
        return len(repository)
    except Exception:
        try:
            return len(_repo_keys(repository))
        except Exception:
            return 0


def _repo_has(repository, key):
    """Return True if *key* is present in a Repository-like object."""
    try:
        return key in repository
    except Exception:
        try:
            return key in _repo_keys(repository)
        except Exception:
            return False


def _safe_get(repository, key):
    """Safely retrieve an item from a Repository by key.

    Returns ``None`` on any failure instead of raising.
    """
    try:
        return repository[key]
    except Exception:
        return None


def _count_elements(part):
    """Return the number of elements on a Part (never raises).

    ``part.elements`` is normally a ``MeshElementArray`` that supports
    ``len()``.  A defensive fallback via ``.keys()`` is provided in case the
    container does not support ``len()`` directly.
    """
    elements = getattr(part, "elements", None)
    if elements is None:
        return 0
    try:
        return len(elements)
    except TypeError:
        pass
    try:
        return len(list(elements.keys()))
    except Exception:
        return 0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate_model(model, job_name=None):
    """Validate model completeness before submitting an Abaqus job.

    Parameters
    ----------
    model : Model
        An Abaqus ``Model`` object, e.g. ``mdb.models['Model-1']``.
    job_name : str, optional
        If provided, verify that a job with this name exists in ``mdb.jobs``.

    Returns
    -------
    dict
        A dictionary with the following keys::

            {
                "valid": bool,        # True if all blocking checks pass
                "errors": list,       # List of error strings (blocking issues)
                "warnings": list,     # List of warning strings (non-blocking)
                "info": dict,         # Summary info about the model
            }

    Checks performed
    ----------------
    1. Material check           -- at least one material in ``model.materials``
    2. Section check            -- at least one section in ``model.sections``
    3. Section assignment check -- every part has ``sectionAssignments``
    4. Assembly check           -- ``model.rootAssembly.instances`` non-empty
    5. Step check               -- at least one step beyond 'Initial'
    6. BC check                 -- at least one boundary condition
    7. Load check               -- at least one load (non-blocking warning)
    8. Mesh check               -- every part has elements
    9. Job check                -- (optional) job exists in ``mdb.jobs``
    """
    errors = []
    warnings = []
    info = {}

    # Guard against a None model up front so the rest of the checks can
    # assume *model* is a real object.
    if model is None:
        errors.append("Model is None; no model object was provided.")
        return {
            "valid": False,
            "errors": errors,
            "warnings": warnings,
            "info": info,
        }

    # ------------------------------------------------------------------
    # 1. Material check
    # ------------------------------------------------------------------
    try:
        material_keys = _repo_keys(model.materials)
        info["material_count"] = len(material_keys)
        info["materials"] = material_keys
        if len(material_keys) == 0:
            errors.append(
                "Material check failed: no materials defined in "
                "model.materials. At least one material is required."
            )
    except Exception as exc:
        errors.append(
            "Material check failed: could not access model.materials (%s)"
            % _safe_str(exc)
        )

    # ------------------------------------------------------------------
    # 2. Section check
    # ------------------------------------------------------------------
    try:
        section_keys = _repo_keys(model.sections)
        info["section_count"] = len(section_keys)
        info["sections"] = section_keys
        if len(section_keys) == 0:
            errors.append(
                "Section check failed: no sections defined in "
                "model.sections. At least one section is required."
            )
    except Exception as exc:
        errors.append(
            "Section check failed: could not access model.sections (%s)"
            % _safe_str(exc)
        )

    # ------------------------------------------------------------------
    # 3. Section assignment check (per part)
    # ------------------------------------------------------------------
    try:
        part_keys = _repo_keys(model.parts)
        info["part_count"] = len(part_keys)
        info["parts"] = part_keys
        missing_assignment = []
        for part_name in part_keys:
            try:
                part = _safe_get(model.parts, part_name)
                if part is None:
                    warnings.append(
                        "Section assignment check: could not retrieve "
                        "part '%s'." % _safe_str(part_name)
                    )
                    continue
                assignments = getattr(part, "sectionAssignments", None)
                if assignments is None:
                    missing_assignment.append(part_name)
                elif _repo_len(assignments) == 0:
                    missing_assignment.append(part_name)
            except Exception as exc:
                warnings.append(
                    "Section assignment check: could not inspect part '%s' "
                    "(%s)" % (_safe_str(part_name), _safe_str(exc))
                )
        if missing_assignment:
            errors.append(
                "Section assignment check failed: the following parts have "
                "no section assignments: %s" % ", ".join(missing_assignment)
            )
        info["parts_missing_section_assignment"] = missing_assignment
    except Exception as exc:
        errors.append("Section assignment check failed: %s" % _safe_str(exc))

    # ------------------------------------------------------------------
    # 4. Assembly check
    # ------------------------------------------------------------------
    try:
        root_assembly = getattr(model, "rootAssembly", None)
        if root_assembly is None:
            errors.append(
                "Assembly check failed: model.rootAssembly is not "
                "available."
            )
        else:
            instance_keys = _repo_keys(root_assembly.instances)
            info["instance_count"] = len(instance_keys)
            info["instances"] = instance_keys
            if len(instance_keys) == 0:
                errors.append(
                    "Assembly check failed: no instances in "
                    "model.rootAssembly.instances. At least one part "
                    "instance is required."
                )
    except Exception as exc:
        errors.append("Assembly check failed: %s" % _safe_str(exc))

    # ------------------------------------------------------------------
    # 5. Step check (beyond 'Initial')
    # ------------------------------------------------------------------
    try:
        step_keys = _repo_keys(model.steps)
        info["step_count"] = len(step_keys)
        info["steps"] = step_keys
        non_initial_steps = [s for s in step_keys if s != "Initial"]
        info["non_initial_step_count"] = len(non_initial_steps)
        if len(non_initial_steps) == 0:
            errors.append(
                "Step check failed: no analysis steps beyond 'Initial' "
                "in model.steps. At least one analysis step is required."
            )
    except Exception as exc:
        errors.append("Step check failed: %s" % _safe_str(exc))

    # ------------------------------------------------------------------
    # 6. Boundary condition check
    # ------------------------------------------------------------------
    try:
        bc_keys = _repo_keys(model.boundaryConditions)
        info["boundary_condition_count"] = len(bc_keys)
        info["boundary_conditions"] = bc_keys
        if len(bc_keys) == 0:
            errors.append(
                "Boundary condition check failed: no boundary conditions "
                "in model.boundaryConditions. At least one BC is required "
                "to prevent rigid-body motion."
            )
    except Exception as exc:
        errors.append(
            "Boundary condition check failed: could not access "
            "model.boundaryConditions (%s)" % _safe_str(exc)
        )

    # ------------------------------------------------------------------
    # 7. Load check (non-blocking warning)
    #
    # A missing load does not necessarily prevent job submission -- some
    # analysis types (e.g. frequency extraction, heat transfer with
    # prescribed temperatures) do not require explicit loads.  Therefore
    # this check produces a *warning* rather than a blocking error.
    # ------------------------------------------------------------------
    try:
        load_keys = _repo_keys(model.loads)
        info["load_count"] = len(load_keys)
        info["loads"] = load_keys
        if len(load_keys) == 0:
            warnings.append(
                "Load check: no loads defined in model.loads. The model "
                "may have no external excitation (non-blocking, but often "
                "indicates an incomplete model)."
            )
    except Exception as exc:
        warnings.append(
            "Load check failed: could not access model.loads (%s)"
            % _safe_str(exc)
        )

    # ------------------------------------------------------------------
    # 8. Mesh check (per part)
    # ------------------------------------------------------------------
    try:
        part_keys = _repo_keys(model.parts)
        unmeshed = []
        for part_name in part_keys:
            try:
                part = _safe_get(model.parts, part_name)
                if part is None:
                    warnings.append(
                        "Mesh check: could not retrieve part '%s'."
                        % _safe_str(part_name)
                    )
                    continue
                if _count_elements(part) == 0:
                    unmeshed.append(part_name)
            except Exception as exc:
                warnings.append(
                    "Mesh check: could not inspect part '%s' (%s)"
                    % (_safe_str(part_name), _safe_str(exc))
                )
        if unmeshed:
            errors.append(
                "Mesh check failed: the following parts have no elements: "
                "%s" % ", ".join(unmeshed)
            )
        info["parts_without_mesh"] = unmeshed
    except Exception as exc:
        errors.append("Mesh check failed: %s" % _safe_str(exc))

    # ------------------------------------------------------------------
    # 9. Job check (optional)
    # ------------------------------------------------------------------
    if job_name is not None:
        try:
            if mdb is None:
                warnings.append(
                    "Job check skipped: mdb is not available (Abaqus "
                    "module not imported). Cannot verify job '%s'."
                    % _safe_str(job_name)
                )
            else:
                jobs_repo = getattr(mdb, "jobs", None)
                if jobs_repo is None:
                    warnings.append(
                        "Job check skipped: mdb.jobs is not available. "
                        "Cannot verify job '%s'." % _safe_str(job_name)
                    )
                else:
                    job_keys = _repo_keys(jobs_repo)
                    info["job_count"] = len(job_keys)
                    info["jobs"] = job_keys
                    if not _repo_has(jobs_repo, job_name):
                        available = ", ".join(job_keys) if job_keys else "(none)"
                        errors.append(
                            "Job check failed: job '%s' not found in "
                            "mdb.jobs. Available jobs: %s"
                            % (_safe_str(job_name), available)
                        )
                    else:
                        info["job_name"] = job_name
        except Exception as exc:
            errors.append("Job check failed: %s" % _safe_str(exc))

    # ------------------------------------------------------------------
    # Final summary
    # ------------------------------------------------------------------
    info["error_count"] = len(errors)
    info["warning_count"] = len(warnings)

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "info": info,
    }


def validate_and_report(model, job_name=None):
    """Validate the model and print a formatted report to stdout.

    Calls :func:`validate_model` and prints a human-readable summary,
    then returns the same result dict.

    Parameters
    ----------
    model : Model
        An Abaqus ``Model`` object.
    job_name : str, optional
        Optional job name to verify.

    Returns
    -------
    dict
        The result dict from :func:`validate_model`.
    """
    result = validate_model(model, job_name=job_name)
    info = result.get("info", {})

    print("=" * 60)
    print("Abaqus Model Pre-Validation Report")
    print("=" * 60)

    # Overall status
    status = "PASS" if result["valid"] else "FAIL"
    print("Overall status : %s" % status)
    print("Errors         : %d" % len(result["errors"]))
    print("Warnings       : %d" % len(result["warnings"]))
    print("-" * 60)

    # Model summary info
    print("Model summary:")
    summary_fields = [
        ("material_count", "Materials"),
        ("section_count", "Sections"),
        ("part_count", "Parts"),
        ("instance_count", "Instances"),
        ("step_count", "Steps (total)"),
        ("non_initial_step_count", "Steps (non-initial)"),
        ("boundary_condition_count", "Boundary conditions"),
        ("load_count", "Loads"),
        ("job_count", "Jobs"),
    ]
    for key, label in summary_fields:
        if key in info:
            print("  %-24s: %s" % (label, info[key]))

    if "parts_missing_section_assignment" in info and info["parts_missing_section_assignment"]:
        print("  %-24s: %s"
              % ("Parts w/o section", ", ".join(info["parts_missing_section_assignment"])))
    if "parts_without_mesh" in info and info["parts_without_mesh"]:
        print("  %-24s: %s"
              % ("Parts w/o mesh", ", ".join(info["parts_without_mesh"])))
    print("-" * 60)

    # Errors (blocking)
    if result["errors"]:
        print("ERRORS (blocking):")
        for i, err in enumerate(result["errors"], 1):
            print("  %d. %s" % (i, err))
    else:
        print("ERRORS (blocking): none")
    print("-" * 60)

    # Warnings (non-blocking)
    if result["warnings"]:
        print("WARNINGS (non-blocking):")
        for i, warn in enumerate(result["warnings"], 1):
            print("  %d. %s" % (i, warn))
    else:
        print("WARNINGS (non-blocking): none")
    print("=" * 60)

    return result


# ---------------------------------------------------------------------------
# Command-line entry point -- validate the first model in mdb when run
# directly inside Abaqus (``abaqus cae noGUI=abaqus_precheck.py``).
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    if not ABAQUS_AVAILABLE:
        print("This script must be run inside Abaqus/CAE "
              "(e.g. abaqus cae noGUI=abaqus_precheck.py).")
        sys.exit(1)

    model_keys = _repo_keys(mdb.models)
    if not model_keys:
        print("No models found in mdb.models.")
        sys.exit(1)

    current_model_name = model_keys[0]
    current_model = mdb.models[current_model_name]
    print("Validating model: %s" % _safe_str(current_model_name))
    validate_and_report(current_model)
