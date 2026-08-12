# SugarPrep Successful-Behavior Migration Plan

Status: local migration and readiness gates complete
Last updated: 2026-08-12

## Objective

Build a new, small SugarPrep implementation that preserves the successful
behavior of three models produced by the highly experimental old SugarPrep:

1. Qwen Cleaner;
2. Gemma typed-layout; and
3. PII NER.

Old SugarPrep is evidence and reference material, not the target architecture.
Its module tree, training framework, research harnesses, compatibility names,
provider abstractions, and experimental workflows do not migrate merely
because one of the successful models once depended on them. They are isolated
as one disposable legacy reference rather than deleted.

The migration preserves observable successful behavior. It does not preserve
the old implementation.

## Product boundary

The three models support two retained product paths.

### Data remediation

- Qwen Cleaner proposes a strict deterministic cleaning plan.
- Deterministic code executes the accepted plan against a copy of the source.
- Gemma proposes a typed Layout from dataset/profile evidence and user intent.
- Deterministic validation accepts or rejects both model candidates.

### PII masking

- PII NER proposes sensitive spans.
- Deterministic code masks those spans into a copy of the source.
- Provenance binds the candidate to the exact input and model result.

Everything else must justify itself as the smallest deterministic support
needed by one of these paths or by the final SugarBot package contract.

## What successful behavior means

The behavioral contracts below are the migration source of truth. Legacy code
is useful only to explain or reproduce these observations.

### Qwen Cleaner

Input behavior:

- receives bounded CSV evidence, observed issues, user cleaning intent, and the
  available deterministic tool vocabulary;
- receives no private drive paths in model-facing content.

Output behavior:

- produces one strict `CleanerToolPlan` candidate;
- uses `execute`, `needs_user_input`, or `cannot_repair` correctly;
- uses only deterministic tools supported by the new implementation;
- preserves unknowns, warnings, diagnostics, and metadata.

Acceptance behavior:

- the strict plan parses without aliases or silent repair;
- execute plans run against an original-preserving copy;
- deterministic validation and source provenance pass;
- retained successful examples reproduce their expected cleaned output;
- the known historical miss is not rewritten as a success.

The new implementation may organize prompts, ports, execution, and evidence
differently. It must not narrow the successful tool behavior to fit a new
abstraction.

### Gemma typed-layout

Input behavior:

- receives bounded dataset/profile evidence and semantic layout guidance;
- resolves time, entity, primary value, included values, metadata, and
  forbidden values.

Output behavior:

- produces a candidate satisfying the seven-field typed-layout contract;
- uses only real profile columns, except allowed `row_index`;
- includes `primary_value_col` in `value_cols`;
- never bypasses deterministic layout validation.

The successful model artifact is the promoted Gemma LoRA/adapter. Its indexed
completion behavior and established typed-output recovery are evidence for the
behavior to preserve, not an instruction to copy the old adapter modules.

GGUF is not a required migration path. A GGUF file may be retained locally as
a deployment derivative, but it does not define success and is not a readiness
gate unless separately proven and explicitly adopted later.

### PII NER

Input behavior:

- receives local text from the exact source candidate.

Output behavior:

- produces scored, typed spans bound to the exact text;
- preserves the model's successful detection of names, email, phone, city,
  and other trained labels.

Acceptance behavior:

- deterministic code combines model spans with allowed deterministic
  detection, resolves overlap, and masks a copy;
- the source remains unchanged;
- evidence records provider identity and model/deterministic finding counts;
- validation proves recognized sensitive values are absent from the candidate.

## Evidence hierarchy

Use evidence in this order:

1. retained successful input, raw model output, accepted output, and provenance;
2. a fresh smoke using the same local model artifact;
3. immutable model manifests and hashes;
4. legacy code needed to explain prompt or output semantics;
5. historical summaries and documentation.

Passing tests written for a replacement abstraction are not parity evidence.
Parser success alone is not model success. A deployment export is not the
original successful model merely because it can load.

## Target implementation

The new implementation lives under `src/sugarprep` and is organized by current
ownership, not legacy namespaces.

- `domain`: immutable values and provenance.
- `profiling`: bounded deterministic evidence.
- `inference`: three model-specific candidate contracts only.
- `transforms`: deterministic plan execution and masking.
- `validation`: authoritative candidate and package gates.
- `artifacts`: candidate, acceptance, manifest, and atomic persistence.
- `workflows`: the two retained product paths.
- `infrastructure`: only concrete local adapters selected for the new runtime.
- `cli`: thin composition for supported public operations.

Do not create a generic model platform, generic text-generation contract,
provider-neutral promotion framework, training distribution, research matrix,
or compatibility namespace unless a retained behavior requires it.

## Treatment of old and failed code

### Old SugarPrep

Old SugarPrep may be abandoned aggressively by the new implementation after
its useful evidence is captured. There is no module-for-module migration
requirement, but old SugarPrep reference material is consolidated rather than
deleted.

- Keep the Phase 0 recovery archive until all three behavioral parity gates
  pass and the new runtime package is inspected.
- Keep model weights, manifests, successful specimens, and hashes outside the
  publishable package.
- Use `_migration/legacy_sugarprep` as the single final home for the old
  SugarPrep implementation and reference material.
- Consolidate old source, training and research code, tools, scripts, docs,
  compatibility namespaces, and runtime copies into that folder, including
  material recoverable only from the Phase 0 archive.
- Do not leave old SugarPrep implementation code in sibling migration folders,
  root tools, runtime copies, or the new `src/sugarprep` tree.
- Keep the legacy folder non-importable, excluded from builds and wheels, and
  disposable as one unit.
- Extract small, path-scrubbed behavioral fixtures when they are needed.
- Do not delete old SugarPrep source or experimental tooling merely because it
  is not migrated; move it into the single legacy folder.
- The three retained model artifacts, their manifests, and canonical behavioral
  specimens are active migration inputs and do not belong in the disposable
  legacy folder.

### Failed migration work

Delete rather than preserve:

- the Phase 5 continuation/promotion research distribution;
- the failed Cleaner continuation adapter and generated runs;
- the narrowed four-tool Cleaner replacement executor;
- generic Cleaner/Layout interfaces that reshape the successful behavior;
- speculative provider, scorecard, benchmark, and compatibility layers; and
- docs, tests, CI jobs, and metadata that authorize those deleted paths.

## Corrective checkpoint

Before adding more runtime behavior:

1. Inventory one canonical successful specimen set for each model.
2. Record model identity, input evidence, raw output, accepted output, and the
   deterministic validation that made it successful.
3. Audit the current `src/sugarprep` changes against those specimens.
4. Remove or demote anything introduced from inference rather than evidence,
   including GGUF-specific ownership if it is not independently required.
5. Freeze path-scrubbed parity fixtures and model-backed smoke commands.

This checkpoint corrects the prior mistake of treating legacy implementation
details and later deployment artifacts as migration requirements.

## Implementation sequence

### A. Behavioral evidence set

- Qwen: retain canonical strict requests/responses for all three stop outcomes
  and at least one successful deterministic execute result.
- Gemma: retain canonical profile/guidance, raw completion, recovered typed
  layout, and deterministic validation result.
- PII: retain canonical text, scored spans, masked copy expectations, and
  source-preservation evidence.

### B. Small model-specific boundaries

- Implement one Qwen candidate boundary.
- Implement one Gemma candidate boundary for the successful LoRA behavior.
- Implement one PII span boundary.
- Do not share a generic generation abstraction merely because Qwen and Gemma
  are both language models.

### C. Deterministic authority

- Implement only the cleaning operations exercised by successful retained
  behavior, expanding from evidence rather than an invented subset.
- Validate all Cleaner plans and outputs.
- Validate all typed layouts against real headers and invariants.
- Mask PII through deterministic copy production and provenance.

### D. Live parity

- Run Qwen on retained requests and compare stop reason, executable semantics,
  provenance, and exact cleaned output.
- Run the promoted Gemma LoRA on retained profile/guidance and compare the
  validated typed layout.
- Run PII NER on retained texts and compare material spans and masked results.

### E. Package readiness

- Run the deterministic preparation and SugarBot package example.
- Run tests, lint, compile, hygiene, and monolith checks.
- Build and inspect the runtime wheel.
- Prove the wheel contains no migration source, training/research code, model
  weights, executables, caches, private paths, or generated data.
- Do not initialize Git or begin branch workflow before these gates pass.

### F. Legacy consolidation

- Restore any previously removed old SugarPrep reference material from the
  Phase 0 archive when needed for a complete inventory.
- Move all old SugarPrep implementation and experimental reference material
  under `_migration/legacy_sugarprep`.
- Remove duplicate old-code copies only after the canonical legacy-folder copy
  is verified.
- Prove the new runtime neither imports nor packages the legacy folder.
- Treat the completed legacy folder as one disposable unit; do not selectively
  depend on files inside it.

## Completion gates

The migration is complete only when:

- all three local model artifacts pass their behavioral parity gates;
- Cleaner execute results and stop outcomes match retained successful evidence;
- Gemma produces a deterministically valid typed layout through the selected
  new LoRA runtime path;
- PII produces source-bound spans and a validated original-preserving masked
  copy;
- the two retained product paths work through the new public boundary;
- `src/sugarprep` contains no capability unrelated to those paths;
- all old SugarPrep implementation and experimental reference material is
  isolated under the single `_migration/legacy_sugarprep` folder rather than
  deleted;
- no runtime import depends on `_migration/legacy_sugarprep`;
- no duplicate old SugarPrep implementation remains elsewhere in the project;
  and
- the publishable runtime package is clean.

## Completion record

The local migration gates passed on 2026-08-12:

- Qwen Cleaner passed live `execute`, `needs_user_input`, and `cannot_repair`
  parity through the complete fourteen-tool deterministic executor;
- Gemma passed exact typed-layout parity through the promoted LoRA completion
  path, without requiring GGUF;
- PII NER reproduced the frozen material spans and exact original-preserving
  masked copy with source-bound evidence;
- 346 regenerated historical Cleaner cases passed deterministic compatibility,
  including 226 exact execute outputs and 120 stop outcomes;
- the published quickstart produced an accepted seven-file SugarBot package
  and passed the package contract with zero findings;
- the runtime suite, lint, compilation, hygiene, and monolith gates passed;
- an isolated wheel build and install passed with 79 entries and no legacy
  source, training/research code, model assets, generated data, or private
  drive paths; and
- 1,527 old-reference files totaling 39,208,927,907 bytes are contained under
  `_migration/legacy_sugarprep`, with no runtime import or package dependency.

After the readiness gates passed, repository work was explicitly authorized on
2026-08-12 and the local tree was connected to the existing GitHub `origin/main`.
External SugarDeploy composition remains separate user-directed work.
