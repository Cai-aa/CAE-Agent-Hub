# Current profile boundary

Supported workflow: actual request → template choice → displayed-parameter confirmation → frozen CaseSpec → YAML → dependency/input checks → detached solve → reference/analytic verification → point export and report.

The model provider is the current AI client, not a service embedded in the solver connector. `events.jsonl` identifies each actor. Future model adapters can call the same tools without changing the solver/verification core. No credentials, API billing or local model weights are required by these tools.

The elastic verification profile is `compression-two-point-v1`. One- and two-process execution are tested on that profile. MPI runs use automatic PdQuickGrid partitioning; the reader combines the full set of rank files by global point/element IDs. Arbitrary process counts, multi-block meshes and independent decomposed Exodus inputs remain unsupported.

Changing geometry, material, damage, contact, horizon or load requires a new reviewed profile with its own reference and validation logic. Do not expand capability claims by editing the example JSON. Damage and contact rules currently reject unsupported choices instead of supplying guesses.

A different correspondence-material candidate was attempted during environment qualification and failed with an Element_Id/STEP_NP1 error. Its failure log is retained outside source control. No correspondence validation is claimed and no original solver source was modified.

## Added fracture demonstration

`notched-tension-damage-v1` is qualified for MPI1 with dt50ns or an explicitly selected half step. See [fracture.md](fracture.md) for source-specific tension/compression thresholds, canonical Text File geometry, independent per-step bond reconstruction, Damage meaning, crack indicator and remaining limits. Existing elastic MPI1/2 behavior is retained. No arbitrary physical override is accepted.
