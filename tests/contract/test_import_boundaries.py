from __future__ import annotations

import ast
from pathlib import Path
import tomllib


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_ROOT = PROJECT_ROOT / "src" / "sugarprep"
DOMAIN_ROOT = RUNTIME_ROOT / "domain"


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_domain_imports_only_domain_and_standard_library() -> None:
    violations: list[str] = []
    for path in sorted(DOMAIN_ROOT.glob("*.py")):
        for imported in _imports(path):
            if imported.startswith("sugarprep.") and not imported.startswith("sugarprep.domain"):
                violations.append(f"{path.name}: {imported}")
            if imported.split(".", 1)[0] in {"pandas", "pyarrow", "polars"}:
                violations.append(f"{path.name}: {imported}")
    assert violations == []


def test_runtime_never_imports_training_distribution() -> None:
    violations = [
        str(path.relative_to(PROJECT_ROOT))
        for path in sorted(RUNTIME_ROOT.rglob("*.py"))
        if any(name == "sugarprep_training" or name.startswith("sugarprep_training.") for name in _imports(path))
    ]
    assert violations == []


def test_runtime_never_imports_repository_tools() -> None:
    violations = [
        str(path.relative_to(PROJECT_ROOT))
        for path in sorted(RUNTIME_ROOT.rglob("*.py"))
        if any(name == "tools" or name.startswith("tools.") for name in _imports(path))
    ]
    assert violations == []


def test_capabilities_do_not_import_concrete_infrastructure() -> None:
    capability_names = ("profiling", "planning", "transforms", "validation", "artifacts", "inference")
    violations: list[str] = []
    for capability_name in capability_names:
        for path in sorted((RUNTIME_ROOT / capability_name).rglob("*.py")):
            for imported in _imports(path):
                if imported == "sugarprep.infrastructure" or imported.startswith("sugarprep.infrastructure."):
                    violations.append(f"{path.relative_to(PROJECT_ROOT)}: {imported}")
    assert violations == []


def test_capability_imports_follow_the_documented_sibling_exceptions() -> None:
    capability_names = {"profiling", "planning", "transforms", "validation", "artifacts", "inference"}
    allowed_siblings = {("artifacts", "validation"), ("validation", "artifacts")}
    violations: list[str] = []
    for owner in sorted(capability_names):
        for path in sorted((RUNTIME_ROOT / owner).rglob("*.py")):
            for imported in _imports(path):
                parts = imported.split(".")
                if len(parts) < 2 or parts[0] != "sugarprep" or parts[1] not in capability_names:
                    continue
                target = parts[1]
                if target != owner and (owner, target) not in allowed_siblings:
                    violations.append(f"{path.relative_to(PROJECT_ROOT)}: {imported}")
    assert violations == []


def test_capabilities_do_not_interpret_dataset_storage_locators() -> None:
    capability_names = ("profiling", "planning", "transforms", "validation", "artifacts", "inference")
    violations = [
        str(path.relative_to(PROJECT_ROOT))
        for capability_name in capability_names
        for path in sorted((RUNTIME_ROOT / capability_name).rglob("*.py"))
        if ".storage_locator" in path.read_text(encoding="utf-8")
    ]
    assert violations == []


def test_planning_has_no_candidate_or_suggestion_module() -> None:
    planning_root = RUNTIME_ROOT / "planning"
    forbidden = [
        str(path.relative_to(PROJECT_ROOT))
        for path in sorted(planning_root.rglob("*.py"))
        if "suggest" in path.stem or "candidate" in path.stem
    ]
    assert forbidden == []


def test_compiler_plan_language_matches_transform_implementation() -> None:
    from sugarprep.planning.compiler import DEFAULT_COMPILATION_POLICY
    from sugarprep.transforms.cells import TRANSFORMS
    from sugarprep.transforms.derivation import DERIVATIONS
    from sugarprep.transforms.rows import ROW_RULES

    assert DEFAULT_COMPILATION_POLICY.transforms == frozenset(TRANSFORMS)
    assert DEFAULT_COMPILATION_POLICY.derivations == frozenset(DERIVATIONS)
    assert DEFAULT_COMPILATION_POLICY.row_rules == frozenset(ROW_RULES)


def test_artifact_bundle_types_have_one_definition_site() -> None:
    definition_sites: dict[str, list[str]] = {
        "ArtifactBundleDraft": [],
        "ArtifactBundle": [],
        "ArtifactManifest": [],
        "AcceptanceDecision": [],
    }
    for path in sorted(RUNTIME_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and node.name in definition_sites:
                definition_sites[node.name].append(path.relative_to(RUNTIME_ROOT).as_posix())
    assert definition_sites == {
        "ArtifactBundleDraft": ["artifacts/bundle.py"],
        "ArtifactBundle": ["artifacts/bundle.py"],
        "ArtifactManifest": ["artifacts/manifest.py"],
        "AcceptanceDecision": ["artifacts/bundle.py"],
    }


def test_runtime_package_is_under_src() -> None:
    import sugarprep

    package_path = Path(sugarprep.__file__).resolve()
    assert package_path.is_relative_to(RUNTIME_ROOT.resolve())


def test_runtime_version_matches_project_metadata() -> None:
    import sugarprep

    project = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    assert sugarprep.__version__ == project["version"]
