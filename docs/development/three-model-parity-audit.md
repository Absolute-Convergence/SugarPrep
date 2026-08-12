# Three-model parity audit

Status: corrective checkpoint completed on 2026-08-12.

This audit classifies the current `src/sugarprep` tree against the canonical
specimens in `tests/fixtures/model_parity`. It does not treat the old SugarPrep
module layout as a migration requirement.

## Frozen evidence

### Qwen Cleaner

- The `execute` specimen is a retained successful runtime capture. It includes
  the exact strict plan, source digest, tool sequence, source CSV, and validated
  output CSV.
- The `needs_user_input` and `cannot_repair` specimens are the sealed reviewed
  stop-boundary cases from the Cleaner promotion benchmark.
- The retained adapter identity is bound by SHA-256. Its recovered historical
  manifest records 232 accepted cases out of 233 and the known miss
  `cleaner_p019_v003`.
- The 2026-08-12 live three-outcome refresh passed after correcting the runtime
  prompt boundary to inject the exact fourteen-tool vocabulary used in the
  successful curriculum. Before that correction, two execute attempts
  consistently invented unsupported tool `date` and were strictly rejected;
  no output was repaired or executed.
- With the proven vocabulary restored, the execute candidate parsed, ran
  through the new executor, passed authoritative validation, and matched the
  frozen CSV bytes exactly. `needs_user_input` and `cannot_repair` both matched
  their stop reason and performed zero source reads or candidate writes.
- This is behavioral parity evidence, not a new full-matrix promotion claim.

### Gemma typed layout

- The specimen contains the retained indexed profile, guidance, raw completion,
  recovery result, and typed prediction.
- The promoted LoRA adapter and base weights are bound by SHA-256.
- A final live 2026-08-12 completion-style LoRA refresh returned the expected
  seven assignment fields and recovered to the specimen prediction exactly.
- The tokenizer still has no chat template. The runtime boundary is therefore
  indexed completion, not generic chat.
- GGUF is not required by the specimen, provider, or parity gate.

### PII NER

- The final live 2026-08-12 model refresh reproduced the exact text digest,
  offsets, labels, and scores for first name, last name, email, phone, and city.
- The expected copy combines model spans with deterministic email/phone
  detection, matches the frozen masked text exactly, and leaves the original
  CSV unchanged with source-bound masking evidence.
- The retained model weights are bound by SHA-256.

## Source classification

| Classification | Current source | Decision |
| --- | --- | --- |
| Keep | `inference/cleaner.py` | Model-specific strict request, plan, stop-reason, and source-binding boundary. |
| Keep | `infrastructure/qwen_cleaner.py` | Local provider for the retained Qwen adapter; candidate-only output. |
| Keep | `inference/layout.py`, `layout_contract.py`, `layout_prompt.py`, `layout_recovery.py` | Exact indexed completion, recovery, and typed validation behavior. |
| Rewritten | `infrastructure/gemma_layout.py` | Now invokes the promoted LoRA through completion-style Unsloth inference. The speculative GGUF HTTP provider was removed. |
| Keep | `inference/pii.py`, `infrastructure/transformers_pii.py` | Source-bound token-classification spans from the retained PII model. |
| Keep | `transforms/masking.py` | Deterministic, original-preserving copy production and provenance; model spans remain candidates. |
| Keep | deterministic domain, profiling, transforms, validation, artifact, workflow, and CLI modules | These are the authoritative non-model boundary required to validate and accept candidates. |
| Remove/leave removed | generic runtime generation, subprocess-provider abstractions, replacement trainer/promotion framework, and GGUF-specific runtime ownership | They are not required by the three successful behavior contracts. |
| Preserve as reference | `_migration/legacy_sugarprep` and remaining old-root material | Do not import or package it. Consolidate it into the one disposable legacy folder after active parity is complete. |

## Cleaner executor checkpoint

The model-independent Cleaner executor now implements all fourteen retained
tool names. It binds the strict plan candidate to the exact source digest,
preserves stop outcomes without writing a copy, creates execute outcomes under
consumer-owned candidate storage, runs an unconditional final parseability
validation, and records the exact tool arguments plus input/output hashes in
the output snapshot provenance.

Verification includes the frozen execute specimen byte-for-byte and focused
behavioral cases for every tool. A disposable reference-oracle audit also
regenerated 346 historical curriculum cases across all 173 legacy patterns:
226 execute cases matched the historical cleaned cell matrices, while 60
`needs_user_input` and 60 `cannot_repair` cases produced no output. This proves
deterministic executor compatibility; it is not evidence that the current
Qwen provider has passed a new model-quality baseline.

The live Qwen, Gemma, and PII behavioral gates now pass. Full package readiness
and legacy consolidation were completed immediately afterward as recorded
below.

## Final local readiness

Package readiness and consolidation are complete as of 2026-08-12.

- The actual `sugarprep prepare` quickstart produced an accepted seven-file
  bundle, and the SugarBot package validator returned zero findings. The smoke
  found one blank record in the published example; that record was removed so
  its explicit fail-on-reject recipe and its data now agree.
- The final isolated wheel contained 79 entries and installed into a fresh
  temporary environment. CLI validation passed. The wheel contained no legacy
  source, training/research code, model files, generated parity data, or
  private drive paths.
- Old staged runtime/model copies, deployment and recovery archives, extracted
  SugarBot CLI assets, and legacy tests were moved without deletion beneath
  `_migration/legacy_sugarprep`. The verified legacy unit contains 1,527 files
  totaling 39,208,927,907 bytes.
- Runtime tests, Ruff, compileall, project hygiene, and the monolith sentinel
  pass after consolidation. Runtime source neither imports nor packages the
  legacy folder.

The SugarPrep-local migration is therefore complete. Git initialization and
external SugarDeploy composition remain separate user-directed work.
