.. _ref_hfss_patch_antenna_workflow:

Run an HFSS patch antenna workflow
==================================

This example shows how to run a complete HFSS microstrip patch antenna workflow with
PyAEDT-MCP tools. All steps were validated live against Ansys AEDT
2026 R1.

.. note::

   Launch AEDT with ``non_graphical=False`` so the GUI is visible and you can
   inspect the antenna geometry, solved mesh, and S11 report interactively in
   the AEDT window.

Tool visibility model
---------------------

PyAEDT-MCP uses a connection-aware visibility model. The MCP client sees a small,
focused tool surface first, and additional tools unlock after an AEDT session
exists. This avoids "tool not available - connect first" round-trips and
reduces token cost.

.. list-table::
   :header-rows: 1
   :widths: 25 75

   * - Stage
     - Tools available
   * - Server start (no AEDT)
     - ``check_aedt_installed``, ``launch_aedt``, ``connect_to_aedt``,
       ``get_guidelines_for``
   * - After ``launch_aedt`` or ``connect_to_aedt``
     - ``check_aedt_status``, ``create_design``, ``open_project``,
       ``save_project``, ``analyze_design``, ``screenshot``,
       ``run_python_code``, ``run_python_script``, and related tools

The tool set expands automatically as part of the launch or connect call
through ``await ctx.enable_components(tags={"requires_connection"})``.

Workflow steps
--------------

Check AEDT installation
~~~~~~~~~~~~~~~~~~~~~~~

**Tool:** ``check_aedt_installed``

.. code-block:: text

   Response:
     AEDT is installed on this system.
     Version: 2026.1
     Executable: C:\Program Files\ANSYS Inc\v261\AnsysEM\ansysedt.exe

Launch AEDT
~~~~~~~~~~~

**Tool:** ``launch_aedt``

.. list-table::
   :header-rows: 1
   :widths: 35 65

   * - Parameter
     - Value
   * - ``non_graphical``
     - ``False``

Launch in graphical mode so you can view the antenna and S11 report in the
GUI.

.. code-block:: text

   Response:
     Successfully launched AEDT
     Version: 2026.1
     gRPC Port: 59661
     PID: 2600
     Startup Time: ~18s

Create HFSS design
~~~~~~~~~~~~~~~~~~

**Tool:** ``create_design``

.. list-table::
   :header-rows: 1
   :widths: 35 65

   * - Parameter
     - Value
   * - ``app_type``
     - ``Hfss``
   * - ``design_name``
     - ``PatchAntenna_Validation``

.. code-block:: text

   Response:
     Successfully created Hfss design
     Design Name: PatchAntenna_Validation
     Project: Project6
     Solution Type: Terminal

Build geometry and boundaries
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Tool:** ``run_python_code``

.. code-block:: python

   from ansys.aedt.core import Hfss
   hfss = Hfss(project=desktop.project_list[0], design="PatchAntenna_Validation", port=desktop.port)

   # Create substrate (40x40x1.6 mm FR4)
   substrate = hfss.modeler.create_box(
       origin=[0, 0, 0],
       sizes=["40mm", "40mm", "1.6mm"],
       name="Substrate",
       material="FR4_epoxy"
   )

   # Create ground plane
   ground = hfss.modeler.create_rectangle(
       orientation="XY",
       origin=[0, 0, 0],
       sizes=["40mm", "40mm"],
       name="Ground"
   )

   # Create patch (24x24 mm centered on substrate)
   patch = hfss.modeler.create_rectangle(
       orientation="XY",
       origin=["8mm", "8mm", "1.6mm"],
       sizes=["24mm", "24mm"],
       name="Patch"
   )

   # Assign PerfE boundaries
   hfss.assign_perfecte_to_sheets(ground.name)
   hfss.assign_perfecte_to_sheets(patch.name)

   objects = [obj.name for obj in hfss.modeler.objects.values()]
   result = "Geometry and boundaries created. Objects: {}".format(objects)

.. code-block:: text

   Response: Geometry and boundaries created. Objects: ['Substrate', 'Ground', 'Patch']

Add feed line, lumped port, and air box
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Tool:** ``run_python_code``

.. code-block:: python

   from ansys.aedt.core import Hfss
   hfss = Hfss(project=desktop.project_list[0], design="PatchAntenna_Validation", port=desktop.port)

   # Feed line (3mm wide, centered in X, from y=0 to patch edge at y=8mm)
   feed_x = (40 - 3) / 2
   feed = hfss.modeler.create_rectangle(
       orientation="XY",
       origin=["{:.1f}mm".format(feed_x), "0mm", "1.6mm"],
       sizes=["3mm", "8mm"],
       name="FeedLine"
   )
   hfss.assign_perfecte_to_sheets(feed.name)

   # Feed port face (YZ plane at y=0, spans ground to feedline)
   feed_port = hfss.modeler.create_rectangle(
       orientation="YZ",
       origin=["{:.1f}mm".format(feed_x), "0mm", "0mm"],
       sizes=["1.6mm", "3mm"],
       name="FeedPort"
   )

   # Lumped port with Ground reference
   hfss.lumped_port(
       assignment="FeedPort",
       name="Port1",
       reference=["Ground"],
       integration_line=1
   )

   # Air box + radiation boundary
   airbox = hfss.modeler.create_box(
       origin=["-15mm", "-15mm", "-15mm"],
       sizes=["70mm", "70mm", "31.6mm"],
       name="AirBox",
       material="vacuum"
   )
   hfss.assign_radiation_boundary_to_objects("AirBox")

   objects = [obj.name for obj in hfss.modeler.objects.values()]
   result = "Feed, port, and airbox added. Objects: {}".format(objects)

.. code-block:: text

   Response: Feed, port, and airbox added. Objects: ['FeedLine', 'Substrate', 'Ground', 'Patch', 'FeedPort', 'AirBox']

Create setup and frequency sweep
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Tool:** ``run_python_code``

.. code-block:: python

   from ansys.aedt.core import Hfss
   hfss = Hfss(project=desktop.project_list[0], design="PatchAntenna_Validation", port=desktop.port)

   # Create setup at 2.4 GHz
   setup = hfss.create_setup(name="Setup1")
   setup.props["Frequency"] = "2.4GHz"
   setup.props["MaximumPasses"] = 6
   setup.props["MaxDeltaS"] = 0.02
   setup.update()

   # Add linear step sweep 1-4 GHz
   sweep = hfss.create_linear_step_sweep(
       setup="Setup1",
       unit="GHz",
       start_frequency=1.0,
       stop_frequency=4.0,
       step_size=0.05,
       name="Sweep1"
   )

   # Validate design
   valid = hfss.validate_full_design()

   result = "Setup and sweep created. Setup: {}, Sweep: Sweep1, Valid: {}".format(
       setup.name, valid[1] if isinstance(valid, tuple) else valid
   )

.. code-block:: text

   Response: Setup and sweep created. Setup: Setup1, Sweep: Sweep1, Valid: True

Capture pre-solve screenshot
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Tool:** ``screenshot``

The tool returns a PNG file of the AEDT viewport showing the antenna
geometry.

Solve design
~~~~~~~~~~~~

**Tool:** ``run_python_code``

.. code-block:: python

   import time
   from ansys.aedt.core import Hfss
   hfss = Hfss(project=desktop.project_list[0], design="PatchAntenna_Validation", port=desktop.port)

   hfss.save_project()
   t0 = time.time()
   solved = hfss.analyze()
   elapsed = time.time() - t0

   result = "Solved: {}, Time: {:.0f}s".format(solved, elapsed)

.. code-block:: text

   Response: Solved: True, Time: 81s

Create S11 report and export results
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Tool:** ``run_python_code``

Because this workflow uses a terminal solution type, use ``St()`` notation
instead of ``S()``.

.. code-block:: python

   import math
   import os
   from ansys.aedt.core import Hfss

   hfss = Hfss(project=desktop.project_list[0], design="PatchAntenna_Validation", port=desktop.port)

   # Create S11 report via native API
   report_module = hfss.odesign.GetModule("ReportSetup")
   report_module.CreateReport(
       "S11_Return_Loss",
       "Terminal Solution Data",
       "Rectangular Plot",
       "Setup1 : Sweep1",
       ["Domain:=", "Sweep"],
       ["Freq:=", ["All"]],
       ["X Component:=", "Freq", "Y Component:=", ["dB(St(Port1_T1,Port1_T1))"]]
   )

   # Export Touchstone for data analysis
   snp_path = r"D:\ANSYS-DEV\screenshots\PatchAntenna_Validation.s1p"
   os.makedirs(os.path.dirname(snp_path), exist_ok=True)
   hfss.export_touchstone(setup="Setup1", sweep="Sweep1", output_file=snp_path)

   # Parse S1P (MA format: freq_GHz magnitude angle_deg)
   with open(snp_path, "r") as f:
       lines = f.readlines()
   data = [l.strip() for l in lines if l.strip() and not l.startswith("!") and not l.startswith("#")]
   min_s11, min_freq = 999, 0
   for line in data:
       parts = line.split()
       if len(parts) >= 3:
           freq, mag = float(parts[0]), float(parts[1])
           db = 20 * math.log10(mag) if mag > 0 else -100
           if db < min_s11:
               min_s11, min_freq = db, freq

   # Export report image
   jpg_path = r"D:\ANSYS-DEV\screenshots\S11_Report_Validation.jpg"
   report_module.ExportImageToFile("S11_Return_Loss", jpg_path, 1920, 1080)

   result = "S11 Report created! Resonance: {:.4f} GHz, S11 = {:.2f} dB".format(min_freq, min_s11)

.. code-block:: text

   Response: S11 Report created! Resonance: 2.8000 GHz, S11 = -5.22 dB

Capture post-solve screenshot
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

**Tool:** ``screenshot``

The tool returns a PNG file that shows the ``S11_Return_Loss`` report in the AEDT
GUI.

Clear AEDT (optional)
~~~~~~~~~~~~~~~~~~~~~

**Tool:** ``clear_aedt``

.. code-block:: text

   Response: AEDT state cleared. Closed 1 project(s).
