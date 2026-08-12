# Deterministic Preparation Checkpoint

The retained deterministic path is implemented under `src/sugarprep`:

```text
DatasetRef -> DatasetSnapshot -> DatasetProfile
Recipe -> PreparationPlan -> PreparationResult
ResultValidationReport -> ArtifactBundleDraft
BundleValidationReport -> explicit AcceptanceDecision
ArtifactWriter.commit -> ArtifactBundle
```

Profiling, planning, transforms, validation, artifacts, workflows, and concrete
CSV/file adapters have one owner each. Inputs are immutable, transformations
produce candidate copies, and only an explicit acceptance decision authorizes
an atomic bundle commit.

The supported runtime CLI is `profile`, `prepare`, and `validate`. Compatibility
imports, deployment commands, model training, generic research infrastructure,
and unproven runtime capabilities are outside this checkpoint.

The publishable quickstart and exact SugarBot package contract are the parity
gates for this retained path.
