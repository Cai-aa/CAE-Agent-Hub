Usage examples
==============

This page shows example prompts you can use with different Lumerical products.

Ansys Lumerical FDTD™
---------------------

.. code:: text

    Create a simple straight waveguide simulation.
    The waveguide is silicon with a cross section of 500nm width and 220nm height, sitting on a 2um thick SiO2 substrate.
    The waveguide should be 10um long. Use air cladding above. Simulate at 1550nm wavelength with a TE mode source.
    Add a port source at the input and port monitors at both the input (for reflection) and output (for transmission) to measure S-parameters.
    Run the simulation and extract the S-parameters from the output port.

Ansys Lumerical MODE™
---------------------

.. code:: text

    Use Lumerical MODE's FDE solver to find the effective index and loss for the fundamental TE and TM modes for a 220 nm x 500 nm silicon waveguide bend with a bend radius of 10 micron.
    Use standard SOI layer stack with air cladding. Set the simulation wavelength to 1550 nm. Use PML boundary conditions to capture bending losses.
    Set the simulation so we can get the group index as well and then run the simulation and give me the mode properties for the fundamental TE and TM modes.

Ansys Lumerical Multiphysics™
-----------------------------

.. code:: text

    Set up a 3D HEAT simulation of a 10 um long gold wire with a 2 um x 2 um cross section with silver contacts on both ends. The wire is surrounded by SiO2 in all direction.
    Use a simulation region of 20 x 20 x 20 um^3. Keep the default insulating boundary condition for all simulation surfaces and only use a temperature boundary condition
    at the bottom surface to keep it at 300 K (use the 'simulation region' surface type and enable for 'z min'). Use the 'thermal and conductive' solver physics and
    use voltage boundary conditions on the contacts to apply 10 mV across the wire and find the maximum temperature on the wire.

Ansys Lumerical INTERCONNECT™
-----------------------------

.. code:: text

    Create a simple circuit in INTERCONNECT by connecting a CW laser to a straight waveguide from the element library. Set the laser wavelength to 1550 nm.
    Set the waveguide length to 500 um, neff to 2.7, ng to 3.9, loss to 5000 dB/m. Use an oscilloscope at the end of the circuit to record the optical signal
    and report the loss in dB from simulation result.
