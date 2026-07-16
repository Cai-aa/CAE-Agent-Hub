# -*- coding: utf-8 -*-
"""
Abaqus API Helpers - High-level wrappers for common Abaqus API operations.

This module is designed to run inside the Abaqus/CAE kernel (Python 2.7.15 for
Abaqus 2020). It wraps frequently-used Abaqus API calls in robust, type-safe
helpers that work around the strict (and sometimes poorly documented) type
requirements of the Abaqus Python API.

Key type pitfalls handled by this module
-----------------------------------------
* ``SectionAssignment`` requires a ``Region`` object (built from
  ``regionToolset.Region``), **not** a raw ``CellArray``. Passing
  ``part.cells`` directly raises a cryptic (often Chinese-language on Chinese
  Windows) type error.
* ``DisplacementBC`` requires a ``Set`` object as its ``region`` argument,
  **not** a ``Region`` or ``CellArray``.
* ``Pressure`` requires a ``Surface`` object as its ``region`` argument,
  **not** a ``Set`` or ``Region``.
* ``job.writeInput()`` is the correct method name (there is no
  ``writeInputFile``).
* ``frame.fieldOutputs`` is a ``Repository`` object; you must iterate with
  ``.keys()`` rather than treating it as a list or dict.
* ``odbDisplay.setPrimaryVariable`` for stress requires
  ``refinement=(INVARIANT, 'Mises')`` to select the von Mises invariant.

The module is self-contained: it does **not** import from ``abaqus_mcp_compat``
because that package may not be available in the Abaqus kernel environment.
"""

from __future__ import print_function

import sys

# ---------------------------------------------------------------------------
# Abaqus kernel imports.
# Wrapped in try/except so the file can be syntax-checked outside the Abaqus
# kernel (e.g. in a standard CPython interpreter). At runtime inside Abaqus
# these imports will always succeed.
# ---------------------------------------------------------------------------
try:
    from abaqusConstants import *  # noqa: F401,F403  (OFF, SET, INVARIANT, CONTOURS_ON_DEF, PNG, ...)
except ImportError:
    pass

try:
    import regionToolset
except ImportError:
    regionToolset = None

try:
    from odbAccess import openOdb  # noqa: F401
except ImportError:
    openOdb = None

try:
    from abaqus import mdb, session  # noqa: F401
except ImportError:
    mdb = None
    session = None

# ---------------------------------------------------------------------------
# Python 2/3 compatibility (self-contained, no external compat layer).
# Abaqus 2020 ships Python 2.7.15; standard CPython may be 3.x.
# ---------------------------------------------------------------------------
PY2 = sys.version_info[0] == 2
try:
    string_types = (str, unicode)  # Python 2: str + unicode
except NameError:
    string_types = (str,)  # Python 3: str only


# ===========================================================================
# Internal helpers
# ===========================================================================

def _is_string(value):
    """Return True if *value* is a text string (Py2 str/unicode or Py3 str)."""
    return isinstance(value, string_types)


def _sample_list(values, max_samples):
    """Evenly sample at most *max_samples* items from *values*.

    Returns a list of floats. If the input is shorter than *max_samples* the
    full list is returned (converted to floats). When the input is longer,
    evenly spaced indices are used to avoid bias toward the start of the array.
    """
    n = len(values)
    if n == 0:
        return []
    if n <= max_samples:
        return [float(v) for v in values]
    # Evenly spaced indices.  float() in the denominator avoids integer
    # division truncation on Python 2.7.
    indices = [int(i * n / float(max_samples)) for i in range(max_samples)]
    return [float(values[i]) for i in indices]


def _compute_stats(values):
    """Compute min / max / average statistics for a list of numeric values.

    Returns ``None`` if *values* is empty. Otherwise returns a dict with
    keys ``min``, ``max``, ``avg``, and ``count``.
    """
    if not values:
        return None
    total = 0.0
    count = 0
    vmin = None
    vmax = None
    for v in values:
        fv = float(v)
        total += fv
        count += 1
        if vmin is None or fv < vmin:
            vmin = fv
        if vmax is None or fv > vmax:
            vmax = fv
    return {
        "min": vmin,
        "max": vmax,
        "avg": total / count if count else 0.0,
        "count": count,
    }


# ===========================================================================
# 1. Section assignment
# ===========================================================================

def assign_section(part, section_name):
    """Assign a section to all cells of *part*.

    The Abaqus ``SectionAssignment`` constructor requires a ``Region`` object
    for its ``region`` argument. Passing ``part.cells`` (a ``CellArray``)
    directly raises a type error whose message is often displayed in Chinese
    on Chinese Windows installations. This helper automatically wraps
    ``part.cells`` in a ``regionToolset.Region`` before assignment.

    Parameters
    ----------
    part : abaqus.Part.Part
        The part to which the section will be assigned.
    section_name : str
        Name of an existing section in ``mdb.models[...].sections``.

    Returns
    -------
    abaqus.Part.SectionAssignment
        The created SectionAssignment object.
    """
    if regionToolset is None:
        raise RuntimeError(
            "regionToolset is not available; this function must run inside "
            "the Abaqus kernel."
        )
    if part is None:
        raise ValueError("part must not be None")
    if not _is_string(section_name) or not section_name:
        raise ValueError("section_name must be a non-empty string")

    # Build a Region from the part's cells.  The Region constructor accepts
    # keyword arguments such as cells=, faces=, edges=, vertices=, elements=,
    # nodes=, etc.  Passing part.cells directly to SectionAssignment would
    # fail because it expects a Region, not a CellArray.
    region = regionToolset.Region(cells=part.cells)
    assignment = part.SectionAssignment(region=region, sectionName=section_name)
    print("Assigned section '%s' to part '%s' (%d cells)." % (
        section_name, part.name, len(part.cells)))
    return assignment


# ===========================================================================
# 2. Fixed boundary condition
# ===========================================================================

def create_bc_fixed(model, assembly, name, set_name, vertices=None, faces=None,
                    edges=None, create_step='Initial'):
    """Create a geometry-based Set and apply a fully-fixed DisplacementBC.

    ``DisplacementBC`` requires a ``Set`` object (not a ``Region`` or
    ``CellArray``) as its ``region`` argument. This helper first creates a
    named Set on the assembly from the supplied geometry, then creates a
    ``DisplacementBC`` with ``u1 = u2 = u3 = SET`` (i.e. fully constrained in
    all three translational degrees of freedom).

    At least one of *vertices*, *faces*, or *edges* must be provided.

    Parameters
    ----------
    model : abaqus.Model.Model
        The model that will own the boundary condition.
    assembly : abaqus.Assembly.Assembly
        The root assembly on which the Set is created.
    name : str
        Name for the DisplacementBC.
    set_name : str
        Name for the Set that will be created on the assembly.
    vertices : optional
        A ``VertexArray`` (or similar sequence) of vertices for the Set.
    faces : optional
        A ``FaceArray`` (or similar sequence) of faces for the Set.
    edges : optional
        An ``EdgeArray`` (or similar sequence) of edges for the Set.
    create_step : str, optional
        Step in which the BC is created (default ``'Initial'``).

    Returns
    -------
    tuple
        ``(set_obj, bc_obj)`` - the created Set and DisplacementBC.
    """
    if model is None:
        raise ValueError("model must not be None")
    if assembly is None:
        raise ValueError("assembly must not be None")
    if not _is_string(name) or not name:
        raise ValueError("name must be a non-empty string")
    if not _is_string(set_name) or not set_name:
        raise ValueError("set_name must be a non-empty string")

    # Build keyword arguments for the Set from whichever geometry was supplied.
    set_kwargs = {}
    if vertices is not None:
        set_kwargs["vertices"] = vertices
    if faces is not None:
        set_kwargs["faces"] = faces
    if edges is not None:
        set_kwargs["edges"] = edges
    if not set_kwargs:
        raise ValueError(
            "At least one of vertices, faces, or edges must be provided."
        )

    # DisplacementBC requires a Set object as its region argument.
    set_obj = assembly.Set(name=set_name, **set_kwargs)

    # u1=u2=u3=SET enforces zero displacement in all three translational DOFs.
    bc = model.DisplacementBC(
        name=name,
        createStepName=create_step,
        region=set_obj,
        u1=SET,
        u2=SET,
        u3=SET,
    )
    print("Created fixed BC '%s' using set '%s' in step '%s'." % (
        name, set_name, create_step))
    return set_obj, bc


# ===========================================================================
# 3. Pressure load
# ===========================================================================

def create_pressure(model, assembly, name, surface_name, faces, magnitude,
                    create_step):
    """Create a geometry-based Surface and apply a Pressure load.

    ``Pressure`` requires a ``Surface`` object (not a ``Set`` or ``Region``)
    as its ``region`` argument. This helper first creates a named Surface on
    the assembly from the supplied faces (using ``side1Faces``, i.e. the
    positive/outer normal side), then creates a ``Pressure`` load with the
    given magnitude.

    Parameters
    ----------
    model : abaqus.Model.Model
        The model that will own the load.
    assembly : abaqus.Assembly.Assembly
        The root assembly on which the Surface is created.
    name : str
        Name for the Pressure load.
    surface_name : str
        Name for the Surface that will be created on the assembly.
    faces : sequence
        A ``FaceArray`` (or similar sequence) of faces defining the surface.
    magnitude : float
        Magnitude of the pressure.
    create_step : str
        Step in which the load is created.

    Returns
    -------
    tuple
        ``(surface_obj, load_obj)`` - the created Surface and Pressure.
    """
    if model is None:
        raise ValueError("model must not be None")
    if assembly is None:
        raise ValueError("assembly must not be None")
    if not _is_string(name) or not name:
        raise ValueError("name must be a non-empty string")
    if not _is_string(surface_name) or not surface_name:
        raise ValueError("surface_name must be a non-empty string")
    if faces is None:
        raise ValueError("faces must not be None")
    if not _is_string(create_step) or not create_step:
        raise ValueError("create_step must be a non-empty string")

    # Pressure requires a Surface object as its region argument.
    # side1Faces defines the surface using the positive (outer) normal side.
    surface_obj = assembly.Surface(name=surface_name, side1Faces=faces)

    load = model.Pressure(
        name=name,
        createStepName=create_step,
        region=surface_obj,
        magnitude=float(magnitude),
    )
    print("Created pressure '%s' (magnitude=%g) on surface '%s' in step '%s'." % (
        name, float(magnitude), surface_name, create_step))
    return surface_obj, load


# ===========================================================================
# 4. Write input file
# ===========================================================================

def write_input(job_obj):
    """Write the Abaqus input (.inp) file for *job_obj*.

    Uses ``job.writeInput(consistencyChecking=OFF)`` to skip consistency
    checks. This is useful when the model is intentionally incomplete or when
    you want to inspect the generated input file without a full validation
    pass.

    Note: the correct method name is ``writeInput``; there is no
    ``writeInputFile`` method on Abaqus job objects.

    Parameters
    ----------
    job_obj : abaqus.Job.Job
        The job whose input file will be written.

    Returns
    -------
    str
        The path of the written input file (``job_obj.name + '.inp'``).
    """
    if job_obj is None:
        raise ValueError("job_obj must not be None")
    # consistencyChecking=OFF skips the pre-submit validation so that an
    # input file is produced even if the model is not fully consistent.
    job_obj.writeInput(consistencyChecking=OFF)
    inp_path = job_obj.name + ".inp"
    print("Wrote input file: %s" % inp_path)
    return inp_path


# ===========================================================================
# 5. Submit job
# ===========================================================================

def submit_job(job_obj):
    """Submit *job_obj* and block until it completes.

    Calls ``job.submit(consistencyChecking=OFF)`` followed by
    ``job.waitForCompletion()``. The consistency check is disabled so that
    submission proceeds even if the model has minor inconsistencies that the
    solver itself can tolerate.

    Parameters
    ----------
    job_obj : abaqus.Job.Job
        The job to submit.

    Returns
    -------
    str
        The final job status string.
    """
    if job_obj is None:
        raise ValueError("job_obj must not be None")
    print("Submitting job '%s' ..." % job_obj.name)
    job_obj.submit(consistencyChecking=OFF)
    job_obj.waitForCompletion()
    status = str(getattr(job_obj, "status", "UNKNOWN"))
    print("Job '%s' finished with status: %s" % (job_obj.name, status))
    return status


# ===========================================================================
# 6. Extract results from ODB
# ===========================================================================

def extract_results(odb, step_name, max_samples=500):
    """Extract stress (S) and displacement (U) samples from an ODB step.

    ``frame.fieldOutputs`` is a ``Repository`` object, not a list or dict.
    It must be iterated via ``.keys()``. This helper reads the last frame of
    the specified step, extracts the ``S`` (stress) and ``U`` (displacement)
    field outputs, samples up to *max_samples* values, and computes
    min / max / average statistics.

    For stress, the von Mises invariant (``value.mises``) is used.
    For displacement, the resultant magnitude is used.

    Parameters
    ----------
    odb : odbAccess.Odb
        An open ODB object (e.g. from ``openOdb(path=...)``).
    step_name : str
        Name of the step to read.
    max_samples : int, optional
        Maximum number of sample values to return per field (default 500).

    Returns
    -------
    dict
        Dictionary with keys:
        - ``step_name``: the step name.
        - ``frame_count``: number of frames in the step.
        - ``last_frame_value``: frameValue of the last frame.
        - ``field_outputs``: list of available field output keys.
        - ``stress_sample``: list of sampled von Mises stress values.
        - ``disp_sample``: list of sampled displacement magnitudes.
        - ``stress_stats``: dict with min/max/avg/count, or None.
        - ``disp_stats``: dict with min/max/avg/count, or None.
    """
    if odb is None:
        raise ValueError("odb must not be None")
    if not _is_string(step_name) or not step_name:
        raise ValueError("step_name must be a non-empty string")

    if step_name not in odb.steps:
        raise KeyError("Step '%s' not found in ODB. Available steps: %s" % (
            step_name, list(odb.steps.keys())))

    step = odb.steps[step_name]
    if len(step.frames) == 0:
        raise ValueError("Step '%s' has no frames." % step_name)

    frame = step.frames[-1]
    field_outputs = frame.fieldOutputs

    # fieldOutputs is a Repository; iterate with .keys() rather than treating
    # it as a list or dict.
    available_keys = list(field_outputs.keys())

    result = {
        "step_name": step_name,
        "frame_count": len(step.frames),
        "last_frame_value": float(frame.frameValue),
        "field_outputs": available_keys,
        "stress_sample": [],
        "disp_sample": [],
        "stress_stats": None,
        "disp_stats": None,
    }

    # --- Stress (S) ---
    if "S" in available_keys:
        s_field = field_outputs["S"]
        mises_values = []
        for val in s_field.values:
            try:
                mises = getattr(val, "mises", None)
                if mises is not None:
                    mises_values.append(float(mises))
            except Exception:
                continue
        result["stress_sample"] = _sample_list(mises_values, max_samples)
        result["stress_stats"] = _compute_stats(mises_values)

    # --- Displacement (U) ---
    if "U" in available_keys:
        u_field = field_outputs["U"]
        disp_mags = []
        for val in u_field.values:
            try:
                data = val.data
                # Compute resultant magnitude from all components (typically
                # 3 for 3D, but this is robust to any component count).
                mag = sum(float(d) ** 2 for d in data) ** 0.5
                disp_mags.append(mag)
            except Exception:
                continue
        result["disp_sample"] = _sample_list(disp_mags, max_samples)
        result["disp_stats"] = _compute_stats(disp_mags)

    stress_count = result["stress_stats"]["count"] if result["stress_stats"] else 0
    disp_count = result["disp_stats"]["count"] if result["disp_stats"] else 0
    print("Extracted results from step '%s': %d frames, %d stress values, "
          "%d displacement values." % (step_name, len(step.frames),
                                       stress_count, disp_count))
    return result


# ===========================================================================
# 7. Display stress contour
# ===========================================================================

def display_stress_contour(session, odb, viewport_name='Viewport: 1'):
    """Open an ODB and display the von Mises stress contour in a viewport.

    Sets the primary variable to ``S`` (stress) with
    ``refinement=(INVARIANT, 'Mises')`` to select the von Mises invariant,
    and switches the viewport to ``CONTOURS_ON_DEF`` (contours on the
    deformed shape).

    Parameters
    ----------
    session : abaqus.Session.Session
        The Abaqus session object.
    odb : str or odbAccess.Odb
        Either a path to an ODB file (which will be opened via
        ``session.openOdb``) or an already-open ODB object.
    viewport_name : str, optional
        Name of the target viewport (default ``'Viewport: 1'``).

    Returns
    -------
    odbAccess.Odb
        The ODB object now displayed in the viewport.
    """
    if session is None:
        raise ValueError("session must not be None")

    # Accept either a path string or an ODB object.
    if _is_string(odb):
        odb_obj = session.openOdb(path=odb)
    else:
        odb_obj = odb

    vp = session.viewports[viewport_name]
    vp.setValues(displayedObject=odb_obj)

    # refinement=(INVARIANT, 'Mises') selects the von Mises stress invariant.
    # Omitting the refinement tuple or using the wrong form results in an
    # error or an unexpected component being displayed.
    vp.odbDisplay.setPrimaryVariable(
        variableLabel="S",
        refinement=(INVARIANT, "Mises"),
    )
    # CONTOURS_ON_DEF draws contours on the deformed shape.
    vp.odbDisplay.display.setValues(plotState=CONTOURS_ON_DEF)

    print("Displaying von Mises stress contour in viewport '%s'." % viewport_name)
    return odb_obj


# ===========================================================================
# 8. Capture viewport to PNG
# ===========================================================================

def capture_viewport(session, file_path, viewport_name='Viewport: 1'):
    """Save a viewport image to a PNG file.

    Wraps ``session.printToFile`` with ``format=PNG``.

    Parameters
    ----------
    session : abaqus.Session.Session
        The Abaqus session object.
    file_path : str
        Destination file path for the PNG image.
    viewport_name : str, optional
        Name of the viewport to capture (default ``'Viewport: 1'``).

    Returns
    -------
    str
        The *file_path* that was written.
    """
    if session is None:
        raise ValueError("session must not be None")
    if not _is_string(file_path) or not file_path:
        raise ValueError("file_path must be a non-empty string")

    vp = session.viewports[viewport_name]
    session.printToFile(
        fileName=file_path,
        format=PNG,
        canvasObjects=(vp,),
    )
    print("Saved viewport '%s' to '%s'." % (viewport_name, file_path))
    return file_path


# ===========================================================================
# Public API
# ===========================================================================
__all__ = [
    "assign_section",
    "create_bc_fixed",
    "create_pressure",
    "write_input",
    "submit_job",
    "extract_results",
    "display_stress_contour",
    "capture_viewport",
]
