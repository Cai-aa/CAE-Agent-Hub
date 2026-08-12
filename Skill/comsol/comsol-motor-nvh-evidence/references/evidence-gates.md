# Motor NVH Evidence Gates

## Contents

- Gate A: environment
- Gate B: geometry and selections
- Gate C: materials and physics
- Gate D: mesh
- Gate E: structural modes
- Gate F: electromagnetic source
- Gate G: vibration and acoustics
- Gate H: exports and report
- Release privacy gate

## Gate A: environment

Require:

- COMSOL executable or batch command resolved from explicit input, environment, or ignored private config;
- `comsolcompile` resolved for Java API sources;
- solver-native smoke run proving license checkout;
- required physics interfaces available;
- output and temporary directories writable;
- adequate memory estimate recorded.

Path discovery alone does not prove license availability.

## Gate B: geometry and selections

Require:

- pole, magnet, slot, air-gap, support, housing, acoustic, and PML topology consistent with the intended motor;
- finalization method and identity pairs explicitly recorded;
- all required named selections nonempty;
- no accidental modification of a read-only reference model;
- geometry statistics and at least one overview export.

Treat numeric entity IDs and reference topology counts as diagnostics, not portable selection definitions.

## Gate C: materials and physics

Require:

- every domain assigned exactly the intended material role;
- B-H tables have the expected row counts and units when nonlinear iron is used;
- permanent-magnet recoil permeability and remanence are sourced;
- winding phase sequence, reverse-current subsets, magnet polarity, force-calculation selection, fixed constraints, acoustic-structure boundary, PML, and exterior-field boundary are nonempty;
- all expressions compile without undefined variables.

## Gate D: mesh

Require:

- mesh build completes;
- PML meshing method is appropriate for the acoustic formulation;
- no inverted or zero-size elements;
- minimum quality and element counts exported;
- air gap, magnets, teeth, coupling boundaries, and PML receive intended controls.

Stop before formal solves when Gates A-D fail.

## Gate E: structural modes

Require:

- requested mode count returned;
- modes are finite, positive, and ascending;
- no unintended rigid-body near-zero mode;
- mode shapes are physically interpretable;
- key modes are stable under the chosen mesh check when report-grade validation is requested.

Reference frequency error belongs to a separate audit and must not override a physically valid independent model.

## Gate F: electromagnetic source

Require:

- complete periodic solution exists;
- magnetic flux and force values contain no NaN or Inf;
- alternating magnet polarity and winding phase sequence are verified;
- force harmonics required by the NVH study are readable;
- reuse across speeds is justified by recorded electromagnetic assumptions.

## Gate G: vibration and acoustics

Require smoke validation before full validation.

Smoke requirements:

- every requested speed/harmonic pair has a solver record;
- displacement, acoustic pressure, coupling transfer, PML, and exterior-field evaluation are finite;
- observation coordinates and units are recorded.

Full-sweep requirements:

- speed list and harmonic expression match the run request;
- each Campbell row identifies speed, harmonic, frequency, and SPL;
- missing/unsolved combinations remain null or absent, never `0 dB`;
- no duplicate speed/harmonic pairs;
- resonance peaks can be traced to excitation/modal proximity or another documented mechanism.

## Gate H: exports and report

Require:

- source Java or batch input;
- compilation and solver logs with exit codes;
- checkpoint paths and loadability evidence;
- geometry, mesh, modal, electromagnetic, acoustic, and Campbell exports;
- machine-readable validation summary;
- final report listing assumptions, failures, repairs, and unresolved limitations.

Run:

```powershell
python Skill/comsol/comsol-motor-nvh-evidence/scripts/validate_nvh_exports.py `
  --eigenfrequencies <run-dir>/exports/modes/eigenfrequencies.csv `
  --campbell <run-dir>/exports/campbell/campbell_long.csv `
  --output <run-dir>/validation/nvh_export_validation.json
```

Then inspect the run manifest, solver exit codes, checkpoints, exports, and the
generated validation JSON before writing the final report.

## Release privacy gate

Before committing public files, require:

- no drive-letter or home-directory paths;
- no usernames, email addresses, attachment IDs, tokens, license-server strings, or machine names;
- no `.mph`, `.class`, logs, videos, commercial manuals, or generated full-field datasets;
- examples use placeholders, environment variables, and relative paths;
- all Markdown links resolve;
- repository public audit passes.
