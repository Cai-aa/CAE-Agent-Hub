# Synthetic precracked tensile damage profile

`notched-tension-damage-v1` is a new synthetic demonstration, not an upstream gold-result regression or calibrated material. The geometry is a 40 × 20 × 0.5 mm thin layer with 80 × 40 × 1 material points, spacing 0.5 mm and point volume 1.25e-10 m³. A 3D Elastic constitutive law is applied to one layer with z displacement fixed; do not label it a resolved 3D specimen or a plane-stress solution.

## Build-specific evidence

The installed 1.5.1 Dev source `src/damage/Peridigm_CriticalStretchDamageModel.cpp` requires `Critical Stretch_tension` and `Critical Stretch_compression`, unlike the stock test's single threshold. It irreversibly breaks a bond when its relative length change exceeds +0.001 or is below −1. The compression threshold effectively disables compressive failure here. K=14.9 GPa, G=8.94 GPa, density=2200 kg/m³ and both thresholds are explicitly synthetic; they have not been fitted to a material or derived from measured fracture energy.

`PdQuickGridDiscretization.cpp` explicitly rejects bond filters. `TextFileDiscretization.cpp` accepts x/y/z, block and volume rows, constructs geometric neighbor lists and applies the `Rectangular_Plane` filter. The plane-filter setup follows `test/regression/PrecrackedPlate/PrecrackedPlate.xml`, with new SI geometry. Initial bonds intersecting y=0 and x≤−10 mm are omitted; 354 undirected pairs are omitted and 42,304 retained. Damage initialization is zero on all retained neighborhoods. This is why initial precrack length is not a contour of initial nonzero Damage.

The upper/lower three rows are driven in ±y. Grip displacement is v·t²/(2r) up to ramp r=5 µs and v·(t−r/2) afterwards, with v=1 m/s. Initial velocity is zero, x is free, z fixed, no contact. Use RTC `if/else` bodies in quoted YAML strings. This older parser rejects ternary `?` and wrapped long node-list scalars. The canonical generator addresses those syntax limits without changing physical intent.

## Independent verification

The full 601 saved states (dt=50 ns, duration=30 µs) are retained. Python independently constructs all original neighbor pairs with cKDTree, removes the precrack crossings and checks original neighbor counts. For each saved integration state, it computes bond stretch from actual deformed point coordinates and applies the inspected irreversible failure rule. Broken-pair counts at each point divided by the retained neighbor degree must equal native `Damage` within 1e-10. This is an implementation-consistency check independent of the solver's reported Damage, not an independent experimental prediction.

Require finite fields, correct coordinates/IDs/volumes, full time sequence, prescribed grip displacement, Damage within [0,1], nondecreasing Damage, zero initial Damage, new failed pairs, and spatial advance of the connected crack indicator. The 50% crossing-bond bin criterion is defined before the first successful qualification run: group retained bonds crossing y=0 by their intersection x in 0.5 mm bins, then count contiguous bins from the starter tip for which ≥50% of bonds have broken. Extension ≥1 mm and at least two advancing saved frames are the demonstration acceptance condition. It is a thresholded indicator, not a solver-produced crack surface, and does not describe all branch paths.

The base run has 6,661 newly broken pairs, a 12.5 mm connected extension indicator and 25 advancing integration states. A separate confirmed dt=25 ns MCP run has 1,201 native states, 6,700 failed pairs and the same final indicator. At common times, maximum front-indicator difference is one spacing (0.5 mm), mean-Damage difference is 0.00255009 and final count differs by 0.5821% relative to the finer step. These are descriptive sensitivity measurements; no post-hoc pass threshold or formal temporal convergence claim is made. Spatial refinement remains untested.

## Operation and display

Select this profile through the same start/answer/confirm tools. Optional `time_step_variant: half` requests the explicitly reviewed half step; only MPI1 is qualified for fracture. Other physical overrides are rejected. `points.txt` is part of input identity and canonical repair preserves its snapshot and diff. Never alter thresholds, boundary conditions, horizon or duration as a repair.

Viewer exports 31 actual saved frames including the endpoints, without interpolation; all native states remain available for validation. Show Damage (broken-bond fraction, 0–1) or actual displacement magnitude in m, at displacement scale 1. Label the starter crack separately from the computed front indicator. No invented finite elements, fracture surface, stress or experimental accuracy. Energy/work balance, fracture-energy calibration, contact, arbitrary geometries and MPI fracture remain unverified.
