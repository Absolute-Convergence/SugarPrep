# Examples

Examples must be small, deterministic, safe to publish, and independent of private datasets, local drive paths, model weights, and embedded SugarBot distributions.

The intended deterministic example demonstrates the public contract:

```text
CSV -> DatasetRef -> DatasetSnapshot -> DatasetProfile
Recipe + DatasetProfile -> PreparationPlan
PreparationPlan + DatasetSnapshot -> TransformPipeline -> PreparationResult
PreparationResult -> ResultValidationReport
passing result -> ArtifactBundleDraft -> BundleValidationReport
passing draft + explicit acceptance -> ArtifactWriter.commit -> ArtifactBundle
```

The existing `quickstart/` files and legacy CLI commands are retained as current-state behavioral fixtures during the refactor. They may change when the new workflow and CLI entry points land. Model-backed examples belong in explicitly optional lanes and must state their local runtime requirements.

See [../SugarPrepRefactor.md](../SugarPrepRefactor.md) for the target API and migration checkpoints.
