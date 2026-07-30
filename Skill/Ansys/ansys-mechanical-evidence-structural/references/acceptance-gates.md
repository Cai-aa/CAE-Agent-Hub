# Mechanical Acceptance Gates

All gates below are independent.

1. Mechanical analysis object state is `Solved`.
2. MAPDL output reports normal termination and no fatal error.
3. The expected `.rst` exists and is nonempty.
4. Applied loads and support reactions balance within a stated tolerance; use 1% as a default preliminary gate.
5. Mesh statistics and relevant quality metrics are recorded.
6. Requested result objects report solved values and export without error.
7. At least one numeric CSV/JSON export and one native result image exist.
8. Assumptions and known singularities are documented.

Do not use a single global skewness or stress maximum without interpretation.
For contact/nonlinear work, also report contact status, penetration, convergence
substeps, force residuals, and whether weak springs or stabilization were active.

Use:

- `functional-validation` for a successful Mechanical/PyMechanical probe.
- `engineering-draft` for a real solve satisfying gates 1-7.
- `report-grade` only after mesh/contact sensitivity and an analytical,
  experimental, or benchmark comparison.
