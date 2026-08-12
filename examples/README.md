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

The `quickstart/` files exercise the current deterministic recipe, plan,
candidate, validation, and explicit-acceptance path. Model-backed examples
belong in explicitly optional lanes and must state their local runtime
requirements.

See the
[migration accomplishment record](../docs/development/migration-accomplishments.md)
for the preserved behavior and completed runtime architecture.
