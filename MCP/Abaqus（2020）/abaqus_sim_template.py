# -*- coding: utf-8 -*-
"""
Abaqus Static Analysis Simulation Template
==========================================

A reusable Python 2.7 template script for static structural analysis in
Abaqus/CAE.  Run via **File > Run Script** inside Abaqus, or from the
command line with::

    abaqus cae noGUI=abaqus_sim_template.py

This template demonstrates best practices learned from extensive debugging
of the Abaqus Python API on Chinese Windows installations:

* ``from __future__ import print_function`` for Py2/Py3 print compatibility.
* ASCII-only working-directory paths -- Chinese characters such as
  "abaqus仿真" are corrupted by Python 2.7's file-system layer on Chinese
  Windows, leading to cryptic "file not found" errors.
* High-level helpers from ``abaqus_api_helpers.py`` that wrap the strict
  Abaqus type requirements:
    - ``assign_section(part, section_name)``  -- wraps cells in a Region
      (SectionAssignment requires a Region, not a raw CellArray).
    - ``create_bc_fixed(...)``  -- creates a geometry Set + DisplacementBC
      (DisplacementBC requires a Set, not a Region or CellArray).
    - ``create_pressure(...)``  -- creates a geometry Surface + Pressure
      (Pressure requires a Surface, not a Set or Region).
    - ``write_input(job)``  -- uses ``writeInput(consistencyChecking=OFF)``
      (the method is ``writeInput``, not ``writeInputFile``).
    - ``submit_job(job)``  -- uses ``submit(consistencyChecking=OFF)``.
    - ``extract_results(odb, step_name)``  -- iterates ``fieldOutputs``
      with ``.keys()`` (it is a Repository, not a list or dict).
    - ``display_stress_contour(session, odb)``  -- uses
      ``refinement=(INVARIANT, 'Mises')`` for von Mises stress.
    - ``capture_viewport(session, file_path)``  -- PNG export via
      ``session.printToFile``.
* Pre-validation via ``abaqus_precheck.validate_and_report`` **before**
  submitting the job, so that incomplete models are caught early.
* ``io.open`` with explicit ``encoding="utf-8"`` for all file I/O
  (avoids the GBK default on Chinese Windows + Python 2.7).
* ``json.dumps(ensure_ascii=True)`` for all JSON serialisation (produces
  pure-ASCII output, eliminating GBK/UTF-8 encoding conflicts).

The template builds a simple 1 m cube of steel, fixes the bottom face,
applies a pressure on the top face, meshes it with C3D20R elements, and
runs a static (optionally geometrically nonlinear) analysis.
"""
from __future__ import print_function

# ---------------------------------------------------------------------------
# Standard-library imports (available in both Python 2.7 and 3.x)
# ---------------------------------------------------------------------------
import os
import sys
import io
import json
import glob
import traceback

# ---------------------------------------------------------------------------
# Make the script's own directory importable so that the helper modules
# (abaqus_api_helpers, abaqus_precheck) can be found even when the script
# is executed via File > Run Script inside Abaqus CAE, where the current
# working directory may differ from the script location.
# ---------------------------------------------------------------------------
try:
    _script_dir = os.path.dirname(os.path.abspath(__file__))
except (NameError, OSError):
    # __file__ may not be defined when the script is exec'd interactively.
    _script_dir = os.getcwd()
if _script_dir not in sys.path:
    sys.path.insert(0, _script_dir)

# ---------------------------------------------------------------------------
# Helper-module imports
# ---------------------------------------------------------------------------
from abaqus_api_helpers import (
    assign_section,
    create_bc_fixed,
    create_pressure,
    write_input,
    submit_job,
    extract_results,
    display_stress_contour,
    capture_viewport,
)
from abaqus_precheck import validate_and_report

# ---------------------------------------------------------------------------
# Abaqus kernel imports
#
# These succeed inside the Abaqus kernel (Python 2.7.15 for Abaqus 2020).
# The helper modules wrap their own Abaqus imports in try/except so that
# they can be syntax-checked outside Abaqus; this top-level script assumes
# it is running inside Abaqus.
# ---------------------------------------------------------------------------
from abaqus import mdb, session
from abaqusConstants import *          # noqa: F401,F403  (THREE_D, ON, OFF, SET, ANALYSIS, INVARIANT, CONTOURS_ON_DEF, PNG, ...)
import regionToolset
from mesh import ElemType
from odbAccess import openOdb
import abaqusConstants as _abq_const   # for getattr() lookups by string name

# Python 2/3 text-type alias (for write_json_file compatibility)
try:
    _text_type = unicode  # Python 2
except NameError:
    _text_type = str      # Python 3


# ===========================================================================
# CONFIGURATION  --  edit this dict to customise the simulation
# ===========================================================================
CONFIG = {
    # ASCII-only path!  Do NOT use Chinese characters (e.g. "abaqus仿真")
    # here -- Python 2.7 on Chinese Windows corrupts non-ASCII paths.
    "work_dir": r"C:\Users\40285\Desktop\CAE-Agent-Hub-main\abaqus_sim",
    "model_name": "StaticModel",
    "job_name": "StaticAnalysis",
    "material": {"name": "Steel", "E": 210000.0, "nu": 0.3, "rho": 7850.0},
    "geometry": {"type": "box", "size": 1.0},  # cube with side = 1.0 m
    "mesh": {"element_type": "C3D20R", "seed_size": 0.15},
    "step": {
        "name": "LoadStep",
        "time_period": 1.0,
        "initial_inc": 0.1,
        "max_inc": 0.1,
        "nlgeom": True,
    },
    "bc": {"type": "fixed_bottom"},
    "load": {"type": "pressure_top", "magnitude": 10.0},
}


# ===========================================================================
# Utility functions
# ===========================================================================

def _check_ascii(path):
    """Return True if *path* contains only ASCII characters.

    Non-ASCII characters in file-system paths are corrupted by Python 2.7's
    ``os`` module on Chinese Windows, leading to "file not found" errors
    that are extremely difficult to diagnose.  This check catches the
    problem early with a clear message.
    """
    try:
        if isinstance(path, bytes):
            path.decode("ascii")
        else:
            path.encode("ascii")
        return True
    except (UnicodeEncodeError, UnicodeDecodeError):
        return False


def _json_default(obj):
    """Fallback serialiser for non-JSON-serialisable objects.

    Abaqus Repository objects, Face/Cell objects, etc. are not natively
    JSON-serialisable.  This handler converts them to ``str`` so that
    ``json.dumps`` never raises a TypeError.
    """
    try:
        return str(obj)
    except Exception:
        return repr(obj)


def write_json_file(path, obj):
    """Serialise *obj* to *path* as JSON.

    Uses ``io.open`` with ``encoding="utf-8"`` (requirement: explicit
    encoding for all file I/O) and ``json.dumps(ensure_ascii=True)``
    (requirement: pure-ASCII JSON to avoid GBK/UTF-8 conflicts on Chinese
    Windows + Python 2.7).
    """
    data = json.dumps(obj, ensure_ascii=True, indent=2, default=_json_default)
    # In Python 2.7, json.dumps returns a byte ``str`` when ensure_ascii=True.
    # io.open in text mode expects ``unicode``; decode the pure-ASCII str.
    if hasattr(data, "decode") and not isinstance(data, _text_type):
        data = data.decode("ascii")
    with io.open(path, "w", encoding="utf-8") as f:
        f.write(data)


def clean_old_files(work_dir, job_name):
    """Remove old job output files so the run starts clean.

    Deletes files matching ``<job_name>*<ext>`` for common Abaqus
    extensions, plus ``results.json``.
    """
    extensions = [
        ".inp", ".odb", ".dat", ".msg", ".sta", ".com", ".prt",
        ".sim", ".json", ".png",
    ]
    removed = 0
    for ext in extensions:
        pattern = os.path.join(work_dir, job_name + "*" + ext)
        for filepath in glob.glob(pattern):
            try:
                os.remove(filepath)
                removed += 1
            except OSError:
                pass
    # Also remove the non-prefixed results.json
    extra_path = os.path.join(work_dir, "results.json")
    if os.path.isfile(extra_path):
        try:
            os.remove(extra_path)
            removed += 1
        except OSError:
            pass
    if removed:
        print("Cleaned up %d old file(s)." % removed)


# ===========================================================================
# Main simulation workflow
# ===========================================================================

def main():
    """Execute the full static-analysis workflow.

    Returns 0 on success, 1 on failure.
    """

    # ------------------------------------------------------------------
    # Step 1: Print a clear header with config summary
    # ------------------------------------------------------------------
    cfg = CONFIG
    mat = cfg["material"]
    geom = cfg["geometry"]
    mesh_cfg = cfg["mesh"]
    step_cfg = cfg["step"]
    bc_cfg = cfg["bc"]
    load_cfg = cfg["load"]

    print("=" * 70)
    print("Abaqus Static Analysis Simulation Template")
    print("=" * 70)
    print("Configuration summary:")
    print("  Work dir     : %s" % cfg["work_dir"])
    print("  Model        : %s" % cfg["model_name"])
    print("  Job          : %s" % cfg["job_name"])
    print("  Material     : %s (E=%g, nu=%g, rho=%g)" % (
        mat["name"], mat["E"], mat["nu"], mat["rho"]))
    print("  Geometry     : %s (size=%g m)" % (geom["type"], geom["size"]))
    print("  Mesh         : %s (seed=%g)" % (
        mesh_cfg["element_type"], mesh_cfg["seed_size"]))
    print("  Step         : %s (time=%g, nlgeom=%s)" % (
        step_cfg["name"], step_cfg["time_period"], step_cfg["nlgeom"]))
    print("  BC           : %s" % bc_cfg["type"])
    print("  Load         : %s (magnitude=%g)" % (
        load_cfg["type"], load_cfg["magnitude"]))
    print("=" * 70)

    # ------------------------------------------------------------------
    # Step 2: Validate work directory is ASCII-only, then create it
    # ------------------------------------------------------------------
    work_dir = cfg["work_dir"]
    if not _check_ascii(work_dir):
        print("FATAL ERROR: work_dir contains non-ASCII characters: %s"
              % work_dir)
        print("  Python 2.7 on Chinese Windows corrupts non-ASCII paths.")
        print("  Please use an ASCII-only path (e.g. avoid 'abaqus仿真').")
        return 1

    try:
        os.makedirs(work_dir)
        print("Created work directory: %s" % work_dir)
    except OSError:
        if os.path.isdir(work_dir):
            print("Work directory exists: %s" % work_dir)
        else:
            print("FATAL ERROR: cannot create work directory: %s" % work_dir)
            traceback.print_exc()
            return 1

    # ------------------------------------------------------------------
    # Step 3: Clean up old files
    # ------------------------------------------------------------------
    job_name = cfg["job_name"]
    clean_old_files(work_dir, job_name)

    # ------------------------------------------------------------------
    # Step 4: Abaqus module imports are done at the top of this file.
    #          Change to the work directory so job output lands there.
    # ------------------------------------------------------------------
    original_cwd = os.getcwd()
    os.chdir(work_dir)
    print("Changed working directory to: %s" % work_dir)

    # Build the output dict progressively so partial results can be
    # saved even if a later step fails.
    output = {
        "config": cfg,
        "validation": None,
        "job": {"name": job_name, "status": None},
        "results": None,
        "files": {
            "input": None,
            "odb": os.path.join(work_dir, job_name + ".odb"),
            "png": os.path.join(work_dir, job_name + "_stress.png"),
            "results_json": os.path.join(work_dir, "results.json"),
        },
        "errors": [],
    }

    success = False
    try:
        _run_simulation(cfg, output)
        success = True
    except Exception as exc:
        err_msg = str(exc)
        output["errors"].append(err_msg)
        print("")
        print("FATAL ERROR during simulation: %s" % err_msg)
        traceback.print_exc()
    finally:
        os.chdir(original_cwd)

    # ------------------------------------------------------------------
    # Step 18: Save results.json (always, even on failure)
    # ------------------------------------------------------------------
    results_path = output["files"]["results_json"]
    try:
        write_json_file(results_path, output)
        print("Saved results to: %s" % results_path)
    except Exception as exc:
        print("ERROR: could not write results.json: %s" % str(exc))
        traceback.print_exc()

    # ------------------------------------------------------------------
    # Step 19: Print summary
    # ------------------------------------------------------------------
    print("")
    print("=" * 70)
    if success and not output["errors"]:
        print("Simulation completed successfully.")
    else:
        print("Simulation completed with errors.")
    print("  Job status  : %s" % output["job"]["status"])
    print("  Results JSON: %s" % results_path)
    if output["files"]["input"]:
        print("  Input file  : %s" % output["files"]["input"])
    if os.path.isfile(output["files"]["odb"]):
        print("  ODB file    : %s" % output["files"]["odb"])
    if os.path.isfile(output["files"]["png"]):
        print("  PNG image   : %s" % output["files"]["png"])
    if output["errors"]:
        print("  Errors:")
        for e in output["errors"]:
            print("    - %s" % e)
    print("=" * 70)

    return 0 if (success and not output["errors"]) else 1


def _run_simulation(cfg, output):
    """Run the full simulation pipeline (steps 5-17).

    Raises an exception on any unrecoverable error.  *output* is updated
    in-place so that partial results are available to the caller.
    """
    work_dir = cfg["work_dir"]
    model_name = cfg["model_name"]
    job_name = cfg["job_name"]
    mat = cfg["material"]
    geom = cfg["geometry"]
    mesh_cfg = cfg["mesh"]
    step_cfg = cfg["step"]
    bc_cfg = cfg["bc"]
    load_cfg = cfg["load"]

    size = float(geom["size"])
    half = size / 2.0

    # ------------------------------------------------------------------
    # Step 5: Create model, geometry (box), material, section
    # ------------------------------------------------------------------
    print("\n--- Step 5: Create model, geometry, material, section ---")

    # Remove existing model/job with the same name for idempotency
    if model_name in mdb.models:
        del mdb.models[model_name]
    if job_name in mdb.jobs:
        del mdb.jobs[job_name]

    model = mdb.Model(name=model_name)
    print("Created model: %s" % model_name)

    # --- Geometry: box via sketch + extrude ---
    # Sketch a square in the X-Y plane, then extrude in Z.
    sketch = model.ConstrainedSketch(name="__profile__", sheetSize=10.0)
    sketch.rectangle(point1=(0.0, 0.0), point2=(size, size))
    part = model.Part(name="Part-1", dimensionality=THREE_D,
                      type=DEFORMABLE_BODY)
    part.BaseSolidExtrude(sketch=sketch, depth=size)
    print("Created part 'Part-1': box %.3f x %.3f x %.3f m" % (
        size, size, size))

    # --- Material ---
    material = model.Material(name=mat["name"])
    material.Elastic(table=((float(mat["E"]), float(mat["nu"])),))
    material.Density(table=((float(mat["rho"]),),))
    print("Created material '%s' (E=%g, nu=%g, rho=%g)" % (
        mat["name"], mat["E"], mat["nu"], mat["rho"]))

    # --- Section (using assign_section helper) ---
    # assign_section wraps part.cells in a regionToolset.Region before
    # calling part.SectionAssignment, avoiding the type error that occurs
    # when passing a raw CellArray.
    section_name = "Section-1"
    model.HomogeneousSolidSection(name=section_name, material=mat["name"])
    assign_section(part, section_name)

    # ------------------------------------------------------------------
    # Step 6: Create assembly
    # ------------------------------------------------------------------
    print("\n--- Step 6: Create assembly ---")
    assembly = model.rootAssembly
    instance = assembly.Instance(name="Part-1-1", part=part, dependent=ON)
    print("Created instance 'Part-1-1' (dependent).")

    # ------------------------------------------------------------------
    # Step 7: Create analysis step
    # ------------------------------------------------------------------
    print("\n--- Step 7: Create analysis step ---")
    step_name = step_cfg["name"]
    nlgeom = ON if step_cfg["nlgeom"] else OFF
    model.StaticStep(
        name=step_name,
        previous="Initial",
        timePeriod=float(step_cfg["time_period"]),
        initialInc=float(step_cfg["initial_inc"]),
        maxInc=float(step_cfg["max_inc"]),
        nlgeom=nlgeom,
    )
    print("Created StaticStep '%s' (time=%g, initialInc=%g, maxInc=%g, "
          "nlgeom=%s)" % (
              step_name, step_cfg["time_period"], step_cfg["initial_inc"],
              step_cfg["max_inc"], step_cfg["nlgeom"]))

    # ------------------------------------------------------------------
    # Step 8: Apply BC (using create_bc_fixed helper)
    # ------------------------------------------------------------------
    print("\n--- Step 8: Apply boundary conditions ---")
    if bc_cfg["type"] == "fixed_bottom":
        # Find the bottom face (z = 0) by its centre point.
        # findAt returns a single Face object; the helper passes it to
        # assembly.Set(faces=...), which accepts a single Face.
        bottom_face = instance.faces.findAt((half, half, 0.0))
        if bottom_face is None:
            raise ValueError(
                "Could not find bottom face at (%g, %g, 0.0)" % (half, half))
        create_bc_fixed(
            model=model,
            assembly=assembly,
            name="FixedBC",
            set_name="BottomSet",
            faces=bottom_face,
        )
    else:
        raise ValueError("Unsupported BC type: %s" % bc_cfg["type"])

    # ------------------------------------------------------------------
    # Step 9: Apply load (using create_pressure helper)
    # ------------------------------------------------------------------
    print("\n--- Step 9: Apply loads ---")
    if load_cfg["type"] == "pressure_top":
        # Find the top face (z = size) by its centre point.
        top_face = instance.faces.findAt((half, half, size))
        if top_face is None:
            raise ValueError(
                "Could not find top face at (%g, %g, %g)" % (half, half, size))
        create_pressure(
            model=model,
            assembly=assembly,
            name="PressureLoad",
            surface_name="TopSurface",
            faces=top_face,
            magnitude=float(load_cfg["magnitude"]),
            create_step=step_name,
        )
    else:
        raise ValueError("Unsupported load type: %s" % load_cfg["type"])

    # ------------------------------------------------------------------
    # Step 10: Mesh the part
    # ------------------------------------------------------------------
    print("\n--- Step 10: Mesh ---")
    seed_size = float(mesh_cfg["seed_size"])
    part.seedPart(size=seed_size)
    print("Seeded part with size=%g" % seed_size)

    # Set element type.  The config stores the element code as a string
    # (e.g. "C3D20R"); convert it to the corresponding abaqusConstants
    # constant via getattr.
    elem_type_str = mesh_cfg["element_type"]
    elem_code = getattr(_abq_const, elem_type_str, None)
    if elem_code is None:
        raise ValueError(
            "Unknown element type '%s' -- not found in abaqusConstants."
            % elem_type_str)
    # setElementType requires a Region (not a raw CellArray), just like
    # SectionAssignment.  Build it with regionToolset.Region.
    elem_region = regionToolset.Region(cells=part.cells)
    elem_type = ElemType(elemCode=elem_code)
    part.setElementType(region=elem_region, elemTypes=(elem_type,))
    print("Set element type: %s" % elem_type_str)

    part.generateMesh()
    print("Generated mesh.")

    # ------------------------------------------------------------------
    # Step 11: Create job
    # ------------------------------------------------------------------
    print("\n--- Step 11: Create job ---")
    job = mdb.Job(
        name=job_name,
        model=model_name,
        type=ANALYSIS,
        description="Static analysis template",
    )
    print("Created job: %s" % job_name)

    # ------------------------------------------------------------------
    # Step 12: Run pre-validation BEFORE submitting the job
    # ------------------------------------------------------------------
    print("\n--- Step 12: Pre-validation ---")
    validation_result = validate_and_report(model, job_name=job_name)
    output["validation"] = {
        "valid": validation_result["valid"],
        "errors": validation_result["errors"],
        "warnings": validation_result["warnings"],
        "info": validation_result["info"],
    }

    if not validation_result["valid"]:
        print("")
        print("PRE-VALIDATION FAILED -- stopping before job submission.")
        for err in validation_result["errors"]:
            print("  ERROR: %s" % err)
            output["errors"].append("Validation: %s" % err)
        # Do NOT proceed to write_input / submit_job.
        # results.json will still be saved by main().
        return

    print("Pre-validation passed. Proceeding with job submission.")

    # ------------------------------------------------------------------
    # Step 13: Write input file (using write_input helper)
    # ------------------------------------------------------------------
    print("\n--- Step 13: Write input file ---")
    # write_input calls job.writeInput(consistencyChecking=OFF).
    # Note: the method is writeInput, NOT writeInputFile.
    inp_name = write_input(job)
    inp_path = os.path.join(work_dir, inp_name)
    output["files"]["input"] = inp_path
    print("Input file path: %s" % inp_path)

    # ------------------------------------------------------------------
    # Step 14: Submit job (using submit_job helper)
    # ------------------------------------------------------------------
    print("\n--- Step 14: Submit job ---")
    # submit_job calls job.submit(consistencyChecking=OFF) followed by
    # job.waitForCompletion().
    try:
        job_status = submit_job(job)
        output["job"]["status"] = job_status
    except Exception as exc:
        output["job"]["status"] = "ABORTED"
        output["errors"].append("Job submission failed: %s" % str(exc))
        raise

    # ------------------------------------------------------------------
    # Step 15: Extract results (using extract_results helper)
    # ------------------------------------------------------------------
    print("\n--- Step 15: Extract results ---")
    odb_path = output["files"]["odb"]
    if not os.path.isfile(odb_path):
        raise IOError(
            "ODB file not found after job completion: %s" % odb_path)

    # Open the ODB in read-only mode for data extraction.
    # extract_results iterates frame.fieldOutputs with .keys() (it is a
    # Repository, not a list or dict) and reads S (von Mises) and U
    # (displacement) from the last frame.
    odb = openOdb(path=odb_path, readOnly=True)
    try:
        results = extract_results(odb, step_name)
    finally:
        odb.close()
    output["results"] = results

    # Print key results
    if results.get("stress_stats"):
        s = results["stress_stats"]
        print("  von Mises stress: min=%g, max=%g, avg=%g (count=%d)" % (
            s["min"], s["max"], s["avg"], s["count"]))
    if results.get("disp_stats"):
        d = results["disp_stats"]
        print("  Displacement mag: min=%g, max=%g, avg=%g (count=%d)" % (
            d["min"], d["max"], d["avg"], d["count"]))

    # ------------------------------------------------------------------
    # Step 16: Display stress contour (using display_stress_contour helper)
    # ------------------------------------------------------------------
    print("\n--- Step 16: Display stress contour ---")
    # display_stress_contour opens the ODB via session.openOdb (for
    # display, separate from the data-access ODB above) and sets the
    # primary variable to S with refinement=(INVARIANT, 'Mises').
    # These are non-critical steps -- failures are recorded as warnings
    # but do not abort the script.
    try:
        display_stress_contour(session, odb_path)
    except Exception as exc:
        print("  WARNING: could not display stress contour: %s" % str(exc))
        output["errors"].append("Display: %s" % str(exc))

    # ------------------------------------------------------------------
    # Step 17: Capture viewport (using capture_viewport helper)
    # ------------------------------------------------------------------
    print("\n--- Step 17: Capture viewport ---")
    # capture_viewport calls session.printToFile with format=PNG.
    png_path = output["files"]["png"]
    try:
        capture_viewport(session, png_path)
    except Exception as exc:
        print("  WARNING: could not capture viewport: %s" % str(exc))
        output["errors"].append("Capture: %s" % str(exc))


# ===========================================================================
# Entry point
# ===========================================================================
if __name__ == "__main__":
    sys.exit(main())
