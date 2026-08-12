# PII Detection and Deterministic Masking Checkpoint

The retained PII path separates model evidence from transformation authority:

```text
exact text -> local PII token classifier -> typed span candidate
typed spans + deterministic patterns -> deterministic masking
immutable source -> masked candidate copy + MaskingEvidence
masked snapshot -> normal validation and preparation
```

`inference.pii` owns typed span candidates. `infrastructure.transformers_pii`
owns lazy local model loading. `transforms.masking` and `transforms.pii` own
copy-producing deterministic masking. The original dataset is never modified.

The remaining parity gate is a live run of the retained PII model through the
new provider boundary followed by validation of the masked candidate and its
provenance.
