# AGENTS.md - SugarPrep Agent Compass

Last updated: 2026-08-12.

## Current working point

- Follow `SugarPrepRefactor.md`; it is the controlling successful-behavior
  migration plan.
- Old SugarPrep is experimental reference material, not the target
  implementation.
- Preserve the observable successful behavior of exactly three models: Qwen
  Cleaner, Gemma typed-layout LoRA, and PII NER.
- These models support two product paths: data remediation and PII masking.
- Do not perform module-for-module legacy migration.
- GGUF is not a required success path or readiness gate.
- The failed Phase 5 continuation work and replacement abstractions remain out
  of scope.
- Canonical specimens and the source classification audit are complete. The
  full fourteen-tool deterministic Cleaner executor is implemented with
  source/output provenance and historical reference-oracle compatibility.
- Live parity passes for Qwen execute and both stop outcomes through the full
  executor, Gemma's exact typed layout through completion-style LoRA, and PII
  exact material spans plus original-preserving masking.
- The Qwen boundary must inject and guard the exact sorted fourteen-tool
  `available_tools` context; omitting it caused the model to invent unsupported
  `date` and was the corrected migration defect.
- Legacy consolidation is complete: old staged runtime/model copies, archives,
  extracted SugarBot CLI assets, and legacy namespace tests are all under the
  single `_migration/legacy_sugarprep` disposable reference folder.
- Package readiness and both retained local product-path gates pass. The
  publishable quickstart creates an accepted seven-file SugarBot package, and
  the isolated wheel contains no legacy/training source, model assets,
  generated data, or private drive paths.
- The local migration is complete. The repository is connected to the existing
  GitHub `origin/main`; current work is the SugarPrep repository baseline.
  External SugarDeploy composition remains separate user-directed work.

## Boundaries

- Work only within SugarPrep for this migration.
- SugarStudio is an external composition/deployment owner; do not edit it.
- Use trunk-based development: branch from `main`, keep branches short-lived,
  make validated checkpoint commits, and merge through a documented Pull
  Request after review.
- Model output is candidate-only. Deterministic execution and validation are
  authoritative.
- Preserve source data and produce candidate copies.
- Implement model-specific boundaries; do not invent a generic model platform.
- Preserve successful behavior, not legacy namespaces, code structure,
  research frameworks, or training infrastructure.
- `_migration` is non-importable reference material. Runtime code must not
  depend on it.
- Keep the Phase 0 recovery archive and local model assets until all behavioral
  parity gates pass. Do not package them.
- Do not delete old SugarPrep implementation or experimental reference code.
  Consolidate all of it under the single `_migration/legacy_sugarprep` folder.
- The final legacy folder must be non-importable, excluded from builds, and
  disposable as one unit. No old implementation copy may remain elsewhere.
- Keep the three retained model artifacts, manifests, and canonical behavioral
  specimens outside the disposable legacy folder because they are active
  inputs to the new implementation.

## Verification

Use the SugarPrep-owned environment:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check src tests tools
.\.venv\Scripts\python.exe -m compileall -q src tests tools
.\.venv\Scripts\python.exe tools\check_project_hygiene.py --fail-on warn
.\.venv\Scripts\python.exe tools\check_monoliths.py --fail-on high
```
