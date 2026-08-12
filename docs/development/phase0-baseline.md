# Phase 0 Recovery Baseline

Recorded: 2026-08-09
Scope: SugarPrep only

This is the recovery point for the clean-break refactor defined in [../../SugarPrepRefactor.md](../../SugarPrepRefactor.md). It records behavior and source evidence; it does not make legacy imports, commands, compatibility packages, or wheel contents part of the target architecture.

## Recovery archive

External local archive (not part of this repository):
`SugarPrep-phase0-20260809T183500.zip`.

- Archive entries: 278
- Archive size: 366,015 bytes
- SHA-256: `E998B948299540C8AFA0D0D5395E64BD5FFAFF89E10CFFFB84DB64D33CCA6A44`
- Includes: root project metadata, `sugarprep/`, tests, tools, examples, and the current source/deployment manifest.
- Excludes: virtual environments, caches, bytecode, build output, root model assets, model weights, transfer bundles, embedded executables, and generated data.

Before using the archive, verify its hash and extract it into a new empty recovery directory. Never extract it over the active refactor tree.

## Environment

The baseline uses the SugarPrep-owned environment at `.venv`:

```text
Python 3.11.9
pip 26.2.1
```

The environment is ignored and is not included in the recovery archive.

## Source inventory

- Runtime-package Python files under the legacy `sugarprep/` tree: 181
- Test files: 5
- Source/test/tool/example files excluding bytecode and caches: 215
- Source/test/tool/example size: 1,185,945 bytes
- Baseline tests: 9

The current wheel demonstrates the coupling this refactor must remove. It contains runtime code, training code, research evaluation, recipe search, compatibility trees, deployment commands, and model adapters in one distribution.

## Verification evidence

| Check | Result |
| --- | --- |
| `python -m pytest -q` | PASS: 9 tests |
| `python -m ruff check sugarprep tests tools` | PASS |
| `python tools/check_project_hygiene.py --fail-on warn` | PASS |
| `python tools/check_monoliths.py --fail-on high` | PASS with one design warning |
| `python -m compileall -q sugarprep tests tools` | PASS |
| `python -m sugarprep --help` | PASS |
| `python -m build --wheel --outdir build/phase0-dist` | PASS |

The monolith warning is:

```text
sugarprep/training/cleaner/eval.py: 1,001 lines
```

This is recorded as evidence of the old system's experimental scope. It does
not authorize a training distribution or require migration of model-build
code. Only the three successful model behaviors are retained.

## Baseline wheel

```text
build\phase0-dist\sugarprep-0.1.0-py3-none-any.whl
```

- Size: 285,030 bytes
- SHA-256: `441D58ED9B439197788AC4ED5621A3F258E5AD35DB201CAB2B63DC019AB87AF1`

The wheel is generated evidence and remains ignored. It is not a recovery substitute for the source archive.

## Current public behavior

The legacy module entry point exposes:

```text
profile
compile
prep
validate-package
normalize-wide-periods
unsloth
deploy
```

Only supported SugarPrep runtime behavior will be rebuilt under the target CLI. Training and deployment commands are not runtime CLI requirements.

## Known legacy coupling

- The package is discovered from the repository root rather than `src/`.
- Training and research evaluation ship in the runtime wheel.
- `engine/*` owns canonical implementations while several top-level packages re-export them.
- Compatibility imports are explicitly tested by `tests/test_compatibility_imports.py`.
- The deployment manifest lists training source and compatibility roots as runtime inputs.
- The legacy CLI mixes runtime, training, and deployment commands.
- Recipe candidate generation is currently under `recipes/suggest.py` rather than inference.

These are baseline facts to remove, not compatibility promises.

## External boundary

No external product repository was modified or made part of this baseline. The current entry point, import paths, manifest assumptions, and artifact contracts above are sufficient to identify the installed-package boundary that SugarPrep must publish later. Changes required by an external consumer occur in a separate project after SugarPrep exposes its final public contract.

## Phase 0 exit

Phase 0 is complete when the archive remains readable, the hash matches, and the baseline evidence above is preserved. Later migration phases may deliberately break every legacy command or import recorded here.
