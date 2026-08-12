# SugarPrep

SugarPrep is SugarStudio's local-first data preparation runtime. The old
SugarPrep was highly experimental; this clean implementation preserves only
the successful behavior of the three model artifacts it produced.

## Retained scope

SugarPrep has two product paths:

1. Deterministic data preparation and SugarBot package generation, assisted by
   the proven Qwen Cleaner and Gemma typed-layout models.
2. PII detection through the proven token-classification model, followed by
   deterministic, original-preserving masking.

Those are three model artifacts: Qwen Cleaner, the promoted Gemma layout LoRA,
and PII NER. Model output is candidate evidence; deterministic validation
remains authoritative. GGUF is not a required success path.

Canonical successful specimens for Qwen, Gemma, and PII are frozen. The new
Cleaner runtime now executes all fourteen retained deterministic tools against
an exact source snapshot, creates a separate candidate copy, runs authoritative
final validation, and records model-candidate, tool-argument, input-hash, and
output-hash evidence. Live parity now passes for Qwen execute and both stop
outcomes, Gemma's exact typed layout, and PII spans plus masked copy. Package
readiness also passes, and every old implementation/reference copy is
contained in the local migration worktree under `_migration/legacy_sugarprep`
as one ignored, non-importable disposable folder.

The source-backed
[migration accomplishment record](docs/development/migration-accomplishments.md)
describes what the new repository preserved and how the completed runtime now
works. The finished historical `SugarPrepRefactor.md` plan has been moved out
of the live repository root and archived locally at
`_migration/legacy_sugarprep/SugarPrepRefactor.md`. Because `_migration` is
deliberately ignored, fresh clones contain the accomplishment record, not the
historical working plan.

## Current runtime commands

```powershell
sugarprep profile DATA.csv
sugarprep prepare RECIPE.yaml
sugarprep validate DATA.csv
```

The deterministic path profiles an immutable input, compiles an explicit
recipe, creates a candidate copy, validates it, assembles the canonical
seven-file SugarBot package, and commits only after explicit acceptance.

## Repository shape

```text
SugarPrep/
|-- src/sugarprep/       # runtime package
|-- tests/               # runtime unit, integration, and contract tests
|-- examples/            # publishable deterministic example
|-- docs/                # migration completion and integration contracts
|-- tools/               # repository-maintenance checks only
|-- _migration/          # ignored local-only migration holdings
|   `-- legacy_sugarprep/ # old reference material and completed plan
|-- pyproject.toml
`-- LICENSE
```

There is no generic training distribution. Historical model-build and research
code does not move into the runtime merely because it contributed to a
successful artifact.

Legacy consolidation is complete in the retained local worktree: old staged
runtime/model copies, deployment and recovery ZIPs, extracted SugarBot CLI
assets, legacy namespace tests, and the completed refactor plan are all
contained beneath `_migration/legacy_sugarprep`. Active model artifacts and
path-scrubbed parity evidence remain outside it because they are inputs to the
clean implementation, not disposable old code.

The 2026-08-12 local readiness gate also built and installed the runtime wheel,
ran the published quickstart to an accepted seven-file SugarBot package, and
confirmed that the wheel contains neither legacy/training material nor local
model assets or private paths.

## Verification

Use the SugarPrep-owned environment:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check src tests tools
.\.venv\Scripts\python.exe -m compileall -q src tests tools
.\.venv\Scripts\python.exe tools\check_project_hygiene.py --fail-on warn
.\.venv\Scripts\python.exe tools\check_monoliths.py --fail-on high
```

Do not publish model weights, deployment bundles, generated datasets, caches,
executables, or runtime work products.

## License

Copyright (c) 2026 Absolute-Convergence. All rights reserved. See
[LICENSE](LICENSE).
