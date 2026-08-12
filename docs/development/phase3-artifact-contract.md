# SugarBot Artifact Contract Checkpoint

The deterministic preparation path emits the canonical seven-file package:

- `data.csv`
- `layout.json`
- `profile.json`
- `compiled-plan.json`
- `warnings.json`
- `rejects.csv`
- `manifest.json`

The manifest contains result, bundle-validation, and explicit-acceptance
evidence. Serialization is path-free. The local store stages the complete
package and commits it atomically only after the validated draft and acceptance
decision still match.

`docs/integration/sugarbot.md` and
`tests/fixtures/sugarbot_package_v1.json` are the durable downstream contract.
