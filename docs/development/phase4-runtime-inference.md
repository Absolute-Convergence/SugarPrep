# Three-Model Behavioral Parity Checkpoint

Date: 2026-08-11

SugarPrep is a clean implementation around three successful model behaviors,
not a migration of the experimental system that produced them.

## Behavioral targets

- Qwen Cleaner: bounded evidence to a strict `CleanerToolPlan`, followed by
  deterministic execution and validation.
- Gemma layout LoRA: bounded profile and guidance to a deterministically valid
  seven-field typed Layout candidate.
- PII NER: exact text to scored spans, followed by deterministic,
  original-preserving masking and provenance.

The models do not share a generic inference contract. Each new boundary is
allowed to differ completely from the legacy implementation as long as its
observable successful behavior passes the retained specimens and live smoke.

GGUF is a possible deployment derivative, not one of the required behavioral
targets. It must not drive runtime ownership or readiness gates without a
separate adoption decision.

## Cleaner execution state

The strict Qwen candidate boundary now feeds a separate deterministic executor
covering the complete fourteen-tool vocabulary retained by the successful
Cleaner behavior. Execute outcomes are original-preserving and copy-producing;
stop outcomes never create data. An authoritative final table validation is
always appended, and the result preserves plan unknowns, warnings, diagnostics,
and metadata while binding execution evidence to the provider, candidate,
plan, exact source, exact output, tool calls, and arguments.

The 2026-08-12 live parity pass found that the first clean implementation had
left `available_tools` to callers even though the proven training context
always supplied the exact vocabulary. The model then emitted unsupported
`date`, and the strict parser correctly rejected it. The boundary now injects
and guards the sorted fourteen-tool list itself. With that successful behavior
restored, execute matched the frozen output exactly and both stop outcomes
created no copy. No alias, retry repair, or permissive postprocessing was added.

## Evidence required

For each model retain a path-scrubbed input, raw output, accepted semantic
output, deterministic validation result, model identity, and live smoke
command. Old source is secondary reference material. It is not migrated or
deleted; it is consolidated under `_migration/legacy_sugarprep` as one
non-importable, disposable reference folder.
