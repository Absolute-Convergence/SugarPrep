# SugarPrep

SugarPrep prepares CSV data for SugarBot and provides local tools for cleaning
tabular data and masking personally identifiable information (PII). It is the
data preparation component of SugarStudio, and can also be used as a Python
package or command-line tool.

Use it to inspect a dataset, apply repeatable cleaning rules, and build a
SugarBot input package containing the prepared data, its layout, and a record
of the changes. Preparation writes a separate candidate copy, preserving your
source file. You can review the results before explicitly accepting a package.

## What you can do

- **Understand your data.** Profile CSV headers, row counts, missing values,
  and likely numeric and date columns.
- **Prepare data consistently.** Define a YAML recipe to select and rename
  columns, normalize values, and apply row rules. Validation reports problems
  and records rejected rows.
- **Export for SugarBot.** Generate prepared data and layout metadata together
  with the profile, preparation plan, warnings, and validation evidence.
- **Use local model assistance.** Qwen Cleaner proposes cleaning operations;
  Gemma proposes the layout that identifies time and value columns. Their
  proposals are checked before they can become accepted output.
- **Mask sensitive data.** Detect PII with a local named-entity recognition
  model and apply masking to a separate copy of the dataset.

SugarPrep is currently alpha software. The command-line interface supports
`profile`, `prepare`, and `validate`. Model-assisted cleaning, layout generation,
and PII masking are available through Python integrations; they do not yet
have dedicated CLI commands. SugarBot runs separately and is not required to
try the preparation example below.

## Requirements and installation

The core package requires **Python 3.11 or newer** and **PyYAML 6.x**, which pip
installs automatically. Recipe-based preparation needs no model weights or GPU.

From the repository root, create a virtual environment and install SugarPrep.
These examples use Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe -m sugarprep --help
```

On Linux or macOS, use `.venv/bin/python` in place of
`.\.venv\Scripts\python.exe`. You can also use the `sugarprep` command directly
when the virtual environment is activated.

### Optional model dependencies

Model files are supplied separately; installing SugarPrep does not download
or configure them.

| Feature | Additional requirements |
| --- | --- |
| PII detection | Install `.[pii]` for PyTorch and Transformers, and provide a local token-classification model and tokenizer. |
| Qwen cleaning assistance | Provide the Qwen Cleaner model/adapter and a compatible local Unsloth CLI executable. |
| Gemma layout assistance | Provide the Gemma typed-layout LoRA and its base model, plus a compatible local Unsloth CLI executable. |

To install the Python dependencies for PII detection:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[pii]"
```

The Qwen and Gemma providers take explicit model and executable paths. Their
inference environment must be configured separately; the base installation
and the PII extra do not install Unsloth. Hardware requirements depend on that
inference environment and the model being loaded.

## Try it with the sample data

Run these commands from the repository root. The included example contains
financial price and volume data and a recipe that renames columns, trims the
date field, parses numeric values, and rejects missing dates or negative volume.

First, inspect the input and check its CSV structure:

```powershell
.\.venv\Scripts\python.exe -m sugarprep profile examples/quickstart/data.csv
.\.venv\Scripts\python.exe -m sugarprep validate examples/quickstart/data.csv
```

Then prepare a candidate:

```powershell
.\.venv\Scripts\python.exe -m sugarprep prepare examples/quickstart/data.csv --recipe examples/quickstart/recipe.yaml --output-root out/quickstart
```

Commands print JSON results. Successful preparation returns
`"status": "ready_for_acceptance"` and writes the prepared CSV beneath
`out/quickstart/candidates/`. It does not yet write an accepted SugarBot bundle.
Inspect the candidate data and the validation summary before proceeding.

To prepare and accept a package, include an identity for the acceptance record:

```powershell
.\.venv\Scripts\python.exe -m sugarprep prepare examples/quickstart/data.csv --recipe examples/quickstart/recipe.yaml --output-root out/quickstart --accept-by "your-name"
```

This reruns preparation and accepts the resulting package if validation passes;
it is not a command to accept a previously saved draft. A successful run returns
`"status": "accepted"` and a `bundle_id`. The package is written beneath
`out/quickstart/bundles/` and contains:

| File | Contents |
| --- | --- |
| `data.csv` | Prepared data |
| `layout.json` | Time and value column definitions for SugarBot |
| `profile.json` | Dataset profile |
| `compiled-plan.json` | Recipe and executable preparation plan |
| `warnings.json` | Preparation warnings |
| `rejects.csv` | Rejected-row evidence |
| `manifest.json` | Artifact index, validation results, and acceptance record |

See the [SugarBot package contract](docs/integration/sugarbot.md) for details
about consuming these files.

## Use your own data

Start with [the sample recipe](examples/quickstart/recipe.yaml). Set the expected
input headers, choose the output columns and transformations, and define the
time and value columns in the layout. Adjust the row rules and rejection policy
to fit your data, then pass your CSV and recipe to `prepare`:

```powershell
.\.venv\Scripts\python.exe -m sugarprep prepare path/to/data.csv --recipe path/to/recipe.yaml --output-root out/my-dataset
```

`validate` checks CSV structure; it does not establish that a dataset is suitable
for every analysis. `prepare` also checks the transformed result and the
SugarBot package before allowing acceptance. Commands return exit code `0` on
success, `1` for reported validation failures, and `2` for command or runtime
errors.

For command options, run:

```powershell
.\.venv\Scripts\python.exe -m sugarprep prepare --help
```

## Development

Install the development dependencies and run the tests:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest -q
```

Runtime code lives in `src/sugarprep/`, tests in `tests/`, and sample inputs in
`examples/`. Repository maintenance instructions are in [AGENTS.md](AGENTS.md).

## License

Copyright (c) 2026 Absolute-Convergence. All rights reserved. See
[LICENSE](LICENSE).
