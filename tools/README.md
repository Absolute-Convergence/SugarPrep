# Repository tools

`tools/` contains repository-maintenance checks only:

- `check_project_hygiene.py` rejects generated/private material in publishable
  source;
- `check_monoliths.py` reports separation-of-concerns risks.

Runtime and model-path code must not import from `tools`. Generic training,
benchmark, curriculum, scorecard, and model-matrix programs are outside the
evidence-only migration.
