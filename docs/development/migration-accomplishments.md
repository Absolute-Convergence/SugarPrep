# SugarPrep Successful-Behavior Migration Accomplishments

Status: complete
Completion date: 2026-08-12
Repository: `Absolute-Convergence/SugarPrep`

## Purpose

This document records what the clean-break SugarPrep migration actually
delivered. It is the published completion record for the new repository.

The result was not a module-for-module port of old SugarPrep. The old project
was an experimental workspace containing overlapping runtimes, training and
evaluation code, deployment copies, archives, generated data, and several
abandoned approaches. The migration retained the observable successful
behavior of three proven model artifacts and rebuilt the deterministic runtime
needed to use those artifacts safely.

This record is based on the implementation under [`src/sugarprep`](../../src/sugarprep),
its public contracts, and its unit, integration, and contract tests. The
completed migration plan has been moved out of the live repository root and
archived locally under the ignored disposable legacy folder; see
[Legacy disposition](#legacy-disposition).

## Executive outcome

The new repository contains one dependency-light Python runtime distribution
with two retained product paths:

1. Data remediation and preparation, assisted by Qwen Cleaner and Gemma typed
   layout suggestions.
2. PII detection, assisted by the retained token-classification model, followed
   by deterministic masking.

The three preserved model behaviors are:

| Model artifact | Preserved responsibility | Runtime boundary |
| --- | --- | --- |
| Qwen Cleaner SFT | Propose a strict `CleanerToolPlan`, including safe stop outcomes | [`inference/cleaner.py`](../../src/sugarprep/inference/cleaner.py) and [`infrastructure/qwen_cleaner.py`](../../src/sugarprep/infrastructure/qwen_cleaner.py) |
| Gemma typed-layout LoRA | Convert profile evidence and guidance into a typed layout candidate | [`inference/layout.py`](../../src/sugarprep/inference/layout.py), [`inference/layout_contract.py`](../../src/sugarprep/inference/layout_contract.py), and [`infrastructure/gemma_layout.py`](../../src/sugarprep/infrastructure/gemma_layout.py) |
| PII NER | Propose source-bound sensitive-text spans | [`inference/pii.py`](../../src/sugarprep/inference/pii.py) and [`infrastructure/transformers_pii.py`](../../src/sugarprep/infrastructure/transformers_pii.py) |

The models do not write accepted artifacts, mutate source data, invent runtime
tools, or bypass validation. They produce candidates. Deterministic code owns
execution, masking, validation, artifact assembly, and durable acceptance.

## Runtime architecture delivered

The runtime is now rooted at `src/sugarprep` and split by responsibility:

| Package | Ownership established by the migration |
| --- | --- |
| `domain` | Immutable dataset identity, provenance, recipes, plans, profiles, results, masking evidence, and Cleaner execution evidence |
| `profiling` | Storage-independent deterministic dataset profiling |
| `planning` | Recipe parsing and compilation against an exact profiled snapshot |
| `transforms` | Deterministic preparation, Cleaner execution, masking, scalar transforms, derivations, and row rules |
| `inference` | Model-specific candidate contracts for Cleaner, layout, and PII |
| `validation` | Dataset, result, bundle, and consumer-shaped SugarBot package validation |
| `artifacts` | Canonical document schemas, draft identity, explicit acceptance, and final bundle ownership |
| `workflows` | Thin application sequences that compose capabilities without taking over their ownership |
| `infrastructure` | Local CSV, filesystem, model-provider, and artifact-store adapters |
| `cli` | Thin `profile`, `prepare`, and `validate` commands |

The important runtime sequence is:

```text
source bytes
  -> immutable DatasetSnapshot + SHA-256
  -> deterministic profile
  -> explicit recipe compilation
  -> candidate CSV execution
  -> result validation
  -> candidate artifact-bundle draft
  -> bundle validation
  -> explicit acceptance decision
  -> atomic accepted SugarBot package
```

Model-assisted branches join that sequence only through typed candidates:

```text
Qwen -> CleanerToolPlan candidate -> deterministic Cleaner tools -> candidate CSV
Gemma -> typed layout candidate   -> strict layout validation    -> candidate layout
PII   -> typed span candidate     -> deterministic masking       -> candidate CSV
```

## Common safety foundation

### Exact source binding

[`DatasetRef`](../../src/sugarprep/domain/dataset.py) carries a logical dataset
identity and an opaque storage locator. Capability code does not interpret that
locator. Infrastructure inspects the bytes and produces an immutable
`DatasetSnapshot` containing:

- a SHA-256 content identity;
- ordered unique headers;
- observed row count;
- media type; and
- provenance linking derived copies to exact parent hashes.

Profiling, preparation, Cleaner execution, validation, and masking call
`assert_unchanged` before or after material operations. A source modified after
inspection is rejected instead of being silently processed under stale
evidence.

### Original-preserving candidate output

[`io_csv.py`](../../src/sugarprep/infrastructure/io_csv.py) implements separate
candidate-output adapters for general transforms, Cleaner execution, and PII
masking. Each adapter:

- writes to an owned temporary file;
- enforces the expected row width;
- hashes the completed bytes;
- atomically renames the temporary file into an immutable candidate name;
- records the exact source hash as provenance; and
- aborts and removes incomplete temporary output on failure.

The input file is never overwritten.

### Candidate and acceptance separation

Candidate production and acceptance are separate types and operations.
[`ArtifactBundleDraft`](../../src/sugarprep/artifacts/bundle.py) is content
fingerprinted and contains only `candidate` entries. An
`AcceptanceDecision` binds the actor, time, validation report, draft identity,
and exact draft fingerprint. [`ArtifactWriter`](../../src/sugarprep/artifacts/writer.py)
will not commit unless the validation report, decision, and current draft all
match.

## Data remediation path

### Qwen Cleaner contract

The Cleaner migration preserved a specific model contract rather than a
generic chat interface. [`inference/cleaner.py`](../../src/sugarprep/inference/cleaner.py)
defines:

- request schema `sugarprep.cleaner_runner_request.v1`;
- context schema `sugarprep.cleaner_curriculum_context.v1`;
- plan schema `sugarprep.cleaner_tool_plan.v1`;
- exact root and tool-call keys with no extras;
- exactly three stop reasons: `execute`, `needs_user_input`, and
  `cannot_repair`; and
- the exact fourteen-tool vocabulary implemented by the runtime.

An `execute` result must contain at least one tool call. A
`needs_user_input` result must contain explanatory `unknowns` and no tool calls.
A `cannot_repair` result must contain explanatory `diagnostics` and no tool
calls. Warnings, diagnostics, unknowns, and metadata are preserved on the
result rather than collapsed into a forced success path.

The prompt boundary injects the sorted runtime-owned `available_tools` list and
rejects a caller-supplied list that differs. Path-like keys are removed from
model prompt context. These rules prevent a model from relying on private
machine paths or proposing a tool that deterministic execution does not own.

[`QwenCleanerProvider`](../../src/sugarprep/infrastructure/qwen_cleaner.py)
invokes the retained local adapter through the Unsloth CLI. It validates the
local adapter files, supports the proven chat or completion transports, records
raw output only when explicitly requested, extracts a strict plan JSON object,
and returns that object to the typed inference boundary.

Every `CleanerPlanCandidate` is identified from the provider, exact source
SHA-256, and normalized plan content.

### Fourteen deterministic Cleaner tools

[`transforms/cleaner`](../../src/sugarprep/transforms/cleaner) implements every
tool exposed to Qwen:

| Tool | Deterministic behavior retained |
| --- | --- |
| `detect_file_format` | Detect delimiter and newline style and rank plausible header rows |
| `select_header_row` | Select and validate a viable header record |
| `flatten_multirow_header` | Combine multiple header rows into unique column names |
| `trim_preamble_footer` | Remove preamble, blank, comment, and malformed-width records with quarantine evidence |
| `repair_ragged_rows` | Conservatively pad short rows or trim only trailing empty extras; quarantine unsafe rows |
| `normalize_column_names` | Trim, fill blank names, and suffix duplicates deterministically |
| `normalize_missing_tokens` | Normalize configured missing tokens in selected columns |
| `parse_flexible_number` | Parse currency, separators, percent modes, parentheses, and K/M/B/T suffixes |
| `parse_datetime` | Parse configured or retained date formats into a requested output form |
| `join_datetime_parts` | Derive a date or datetime from source components; quarantine invalid rows |
| `normalize_wide_periods` | Reshape annual, quarterly, and monthly wide columns into normalized period rows |
| `split_compound_column` | Split one source column into explicit new columns; quarantine unsafe splits |
| `deduplicate_rows` | Retain the first exact/keyed row and quarantine later duplicates |
| `validate_parseable_table` | Require non-empty unique headers and exact row widths |

### Cleaner execution and evidence

[`CleanerExecutionPipeline`](../../src/sugarprep/transforms/cleaner/execution.py)
checks that the candidate source hash matches the supplied snapshot and that
the source is unchanged. It executes tool calls in order, requires named
preconditions to have completed, rejects duplicate or reserved call IDs, and
routes only to the fixed handler table above.

Even if the model includes its own validation call, the pipeline appends a
separate reserved authoritative `validate_parseable_table` call after all model
steps. Successful execution creates a candidate copy and records:

- model candidate, provider, and plan identities;
- exact input and output SHA-256 values;
- every call ID, tool name, and argument object;
- rows entering, leaving, and being quarantined by each step;
- step-specific detail and reason counts; and
- the authoritative validation result.

Non-execute stop outcomes do not read, write, or validate a candidate copy.

### Explicit deterministic preparation

The model-assisted Cleaner path is complemented by an explicit recipe path.
[`planning/compiler.py`](../../src/sugarprep/planning/compiler.py) compiles a
recipe against one exact profile and rejects unknown source columns or
unsupported operations.

The implemented preparation language contains:

- transforms: `copy`, `trim`, `parse_numeric`, `parse_flexible_number`,
  `parse_date`, and `map_values`;
- derivations: `join`, `template`, and `datetime_parts`;
- generator: `row_index`;
- row rules: `required`, `numeric_range`, `nonnegative`, `integer_like`,
  `allowed_values`, and `date_range`;
- rule actions: `reject` and `warn`; and
- reject policies: `fail` and `drop`.

[`TransformPipeline`](../../src/sugarprep/transforms/pipeline.py) applies the
compiled plan row by row, creates structured rejection evidence, distinguishes
warnings from fatal errors, and commits only a complete candidate copy.

### Gemma typed-layout contract

The successful Gemma behavior was the promoted LoRA's indexed completion path.
It was not a generic chat path and did not require GGUF.

[`inference/layout.py`](../../src/sugarprep/inference/layout.py) builds a bounded
profile context, assigns deterministic compact labels to visible columns, and
requests exactly seven fields:

- `time_col`;
- `time_kind`;
- `entity_col`;
- `primary_value_col`;
- `value_cols`;
- `metadata_cols`; and
- `forbidden_value_cols`.

The provider requires `prompt_style="indexed"` and
`prompt_transport="completion"`. [`GemmaLayoutProvider`](../../src/sugarprep/infrastructure/gemma_layout.py)
validates the promoted adapter assets and deliberately invokes Unsloth without
a chat system-prompt argument.

[`layout_contract.py`](../../src/sugarprep/inference/layout_contract.py)
requires the exact seven-key schema, rejects markdown and extra keys, supports
only the runtime time kinds, requires `primary_value_col` inside `value_cols`,
forbids overlap with `forbidden_value_cols`, and rejects referenced columns
that are absent from the profile except the allowed `row_index` generator.

Because the proven small model may emit the trained assignment form rather
than strict JSON, [`layout_recovery.py`](../../src/sugarprep/inference/layout_recovery.py)
recovers bounded key/value or embedded-JSON output, resolves indexed labels to
real headers, records recovery warnings, and sends the recovered payload
through the same typed validator. The final `LayoutCandidate` remains bound to
the provider and exact source SHA-256.

## PII detection and masking path

### Retained NER behavior

[`PiiInferenceService`](../../src/sugarprep/inference/pii.py) accepts typed
character spans from one provider, filters them by a configured score, rejects
out-of-range offsets, orders and merges overlaps, removes BIO prefixes from
entity labels, hashes the exact input text, and derives a stable candidate ID
from provider, text hash, and spans.

[`TransformersPiiProvider`](../../src/sugarprep/infrastructure/transformers_pii.py)
loads the retained token-classification model from local files only. It uses
the Transformers `simple` aggregation strategy and selects CUDA when available
or CPU otherwise. Heavy Torch and Transformers dependencies remain confined to
the optional `pii` package extra.

### Deterministic masking

[`MaskingPipeline`](../../src/sugarprep/transforms/masking.py) combines model
spans with deterministic recognition of email addresses, phone numbers, SSNs,
and credential-like token assignments. Deterministic spans win kind ownership
when they overlap model spans. The resulting ranges are replaced with explicit
`[masked KIND]` markers.

For every cell, the pipeline verifies that deterministic PII recognition finds
no residual recognized span after masking. It records:

- the exact source hash;
- row, cell, and masked-cell counts;
- finding counts by kind;
- model provider identity;
- model and deterministic detection counts; and
- the algorithm version.

The masked dataset is a separate candidate snapshot whose provenance points to
the original. The original is not mutated.

## Artifact and SugarBot package path

### Deterministic profile and validation evidence

[`DatasetProfiler`](../../src/sugarprep/profiling/profiler.py) profiles one
unchanged snapshot and records missing values, numeric successes and failures,
integer-like counts, date-like counts, bounded examples, blank rows, and the
profiling stop reason. It supports full profiling and deterministic adaptive
stopping.

Result validation checks plan and input identity, candidate readability,
expected headers, row shape, row count, and exact parent provenance. Bundle
validation then re-derives the draft fingerprint and checks the canonical
artifact set, schemas, filenames, media types, digests, candidate state, and
agreement among plan, profile, result, and validation report.

### Canonical seven-file package

The accepted package contains exactly:

| File | Purpose |
| --- | --- |
| `data.csv` | Prepared candidate data |
| `layout.json` | Raw SugarBot DataSpec |
| `profile.json` | Dataset profile and provenance evidence |
| `compiled-plan.json` | Deterministic compiled preparation plan |
| `warnings.json` | Structured non-fatal warnings |
| `rejects.csv` | Structured rejected-row evidence |
| `manifest.json` | Accepted package identity, artifact map, evidence, and digests |

[`validate_sugarbot_package`](../../src/sugarprep/validation/sugarbot_contract.py)
is deliberately consumer-shaped rather than importing the producer's artifact
constants. It validates the seven-file contract, raw layout shape, data/header
relationships, primary-value membership, manifest/profile source agreement,
row count, schema versions, and canonical artifact mappings.

### Atomic durable commit

[`LocalArtifactStore`](../../src/sugarprep/infrastructure/artifact_store.py)
copies the already-validated candidate and serialized documents into a staging
directory, rechecks every digest, and atomically renames the directory to its
final bundle identity. A partial bundle is removed on failure. The returned
receipt is checked against the accepted manifest before an `ArtifactBundle` is
created.

## Public interface and packaging

The migration replaced legacy command surfaces with three thin commands:

```text
sugarprep profile DATA.csv
sugarprep prepare DATA.csv --recipe RECIPE.yaml --output-root OUTPUT
sugarprep validate DATA.csv
```

`prepare` stops at `ready_for_acceptance` unless `--accept-by` supplies an
explicit actor. It reports validation failures without assembling or committing
an invalid package.

The wheel is built from `src/sugarprep` only. The runtime package:

- requires Python 3.11 or newer;
- keeps the base dependency set to PyYAML;
- isolates Torch and Transformers in the optional `pii` extra;
- excludes tests and local assets from package discovery; and
- exposes no model weights, training distribution, legacy namespaces, or
  repository tools.

Contract tests enforce that domain code stays dependency-light, capabilities
do not import concrete infrastructure, runtime code does not import training or
repository-maintenance tools, storage locators remain opaque outside
infrastructure, and artifact ownership has one definition site.

## Behavioral and repository verification

The published tests preserve the relevant behavior at three levels:

- unit tests cover domain invariants, recipe compilation, profiling, scalar
  transforms, row rules, and all model candidate contracts;
- integration tests cover CSV profiling, explicit preparation, all fourteen
  Cleaner tools, source mismatch detection, stop outcomes, local provider
  invocation, masking, quickstart behavior, and CLI composition; and
- contract tests cover import boundaries, the seven-file SugarBot package, and
  content-bound Qwen/Gemma/PII behavior specimens.

The path-scrubbed fixture manifest freezes:

- Qwen `execute`, `needs_user_input`, and `cannot_repair` outcomes;
- Gemma completion transport, output recovery, and exact typed layout; and
- PII source-bound name, email, phone, and city spans plus masked-copy behavior.

At the completion checkpoint:

- all 78 tests passed;
- Ruff, compile-all, project hygiene, and monolith checks passed;
- the quickstart produced an accepted seven-file SugarBot package;
- an isolated wheel installed and executed successfully;
- the wheel contained no legacy or training source, model assets, generated
  parity data, or private paths; and
- both GitHub CI jobs passed on the initial migration Pull Request.

## What was deliberately not migrated

The following old SugarPrep material is not part of the new runtime:

- legacy namespaces and module structure;
- generic model-platform abstractions;
- failed Cleaner continuation and promotion abstractions;
- historical trainers, dataset builders, research evaluation, and export code;
- duplicated deployment runtimes and embedded SugarBot CLI copies;
- GGUF as a required layout path;
- cloud or SugarDeploy ownership;
- model weights, local bases, caches, executables, generated data, and transfer
  archives; and
- any behavior that bypasses deterministic validation or explicit acceptance.

The migration preserved successful behavior, not every experiment that helped
discover it.

## Legacy disposition

All old implementation, experiments, displaced tests, generated runtime
copies, deployment bundles, source/recovery archives, and the extracted legacy
SugarBot CLI are consolidated locally under:

```text
_migration/legacy_sugarprep/
```

That directory is intentionally ignored by Git, non-importable, excluded from
builds and checks, and disposable as one unit. The active runtime cannot depend
on it.

The completed historical plan was also moved from the repository root to:

```text
_migration/legacy_sugarprep/SugarPrepRefactor.md
```

Because `_migration` is deliberately unpublishable, the archived plan is
available only in the retained local migration worktree and recovery material;
fresh repository clones will not contain it. This document is the published
record of the completed migration and the source code is authoritative for
current behavior.

Active model files remain local under ignored model storage, while their
path-scrubbed behavioral specimens remain published under
[`tests/fixtures/model_parity`](../../tests/fixtures/model_parity).

## Repository state after migration

The live repository now contains only the clean runtime and its maintainable
supporting material:

```text
SugarPrep/
|-- src/sugarprep/       runtime distribution
|-- tests/               unit, integration, contract, and behavior specimens
|-- examples/            deterministic publishable quickstart
|-- docs/                completion, development, and integration records
|-- tools/               repository-maintenance checks only
|-- .github/workflows/   runtime and distribution CI
|-- pyproject.toml       package metadata and build boundary
`-- README.md            repository entry point
```

Future work should use trunk-based development: branch from `main`, keep the
branch short-lived, make validated checkpoint commits, document the change in a
Pull Request, and merge only after review and required checks.
