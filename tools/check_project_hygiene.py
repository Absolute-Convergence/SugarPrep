"""Warn about SugarPrep repository-structure hygiene drift.

The checks distinguish publishable source from ignored local runtime assets.
They are placement and naming guardrails, not a substitute for packaging tests.
"""

from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from pathlib import Path


EXCLUDED_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "DataSets",
    "models",
    "out",
    "reports",
    "_migration",
    "unsloth_compiled_cache",
}

ALLOWED_DUPLICATE_BASENAMES = {
    "__init__.py",
    "README.md",
}

GENERIC_DUPLICATE_BASENAMES = {
    "common.py",
    "constants.py",
    "helpers.py",
    "models.py",
    "schema.py",
    "types.py",
    "utils.py",
}

ALLOWED_TOP_LEVEL_DIRS = {
    ".github",
    ".pytest_cache",
    ".vscode",
    "build",
    "docs",
    "examples",
    "src",
    "tests",
    "tools",
}

ALLOWED_TOP_LEVEL_FILES = {
    ".gitattributes",
    ".gitignore",
    "AGENTS.md",
    "LICENSE",
    "MANIFEST.in",
    "README.md",
    "pyproject.toml",
    "roadmap.md",
}

GENERATED_ROOT_SUFFIXES = {
    ".csv",
    ".jsonl",
    ".parquet",
    ".pt",
    ".zip",
}

ALLOWED_TOOLS_DIRS: set[str] = set()


@dataclass(frozen=True)
class Finding:
    code: str
    path: str
    message: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Warn about SugarPrep project hygiene drift.")
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Repository root to scan.")
    parser.add_argument(
        "--fail-on",
        choices=["none", "warn"],
        default="none",
        help="Exit nonzero when warnings are found.",
    )
    return parser.parse_args()


def check_project(root: Path) -> list[Finding]:
    root = root.resolve()
    findings: list[Finding] = []
    findings.extend(check_top_level(root))
    findings.extend(check_duplicate_basenames(root))
    findings.extend(check_tools_layout(root))
    return sorted(findings, key=lambda item: (item.code, item.path, item.message))


def check_top_level(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    for child in sorted(root.iterdir(), key=lambda path: path.name.lower()):
        if child.name in EXCLUDED_DIRS or child.name.endswith(".egg-info"):
            continue
        if child.is_dir():
            if child.name not in ALLOWED_TOP_LEVEL_DIRS:
                findings.append(
                    Finding(
                        "top_level_dir",
                        child.name,
                        "unexpected top-level directory; place source/artifacts in an explicit runtime lane",
                    )
                )
            continue
        if child.name in ALLOWED_TOP_LEVEL_FILES:
            continue
        if child.suffix in GENERATED_ROOT_SUFFIXES:
            findings.append(
                Finding(
                    "root_generated_file",
                    child.name,
                    "generated-looking file in repo root; use build/, reports/, or models/ lane storage",
                )
            )
            continue
        findings.append(
            Finding(
                "top_level_file",
                child.name,
                "unexpected top-level file; document it or move it under a lane-specific directory",
            )
        )
    return findings


def check_duplicate_basenames(root: Path) -> list[Finding]:
    grouped: dict[str, list[Path]] = {}
    for path in iter_source_files(root):
        grouped.setdefault(path.name, []).append(path)

    findings: list[Finding] = []
    for basename, paths in sorted(grouped.items()):
        if len(paths) <= 1 or basename in ALLOWED_DUPLICATE_BASENAMES:
            continue
        if basename not in GENERIC_DUPLICATE_BASENAMES:
            continue
        rel_paths = ", ".join(str(path.relative_to(root)) for path in paths)
        findings.append(
            Finding(
                "duplicate_generic_basename",
                basename,
                f"generic source basename appears in multiple lanes: {rel_paths}",
            )
        )
    return findings


def check_tools_layout(root: Path) -> list[Finding]:
    tools_dir = root / "tools"
    if not tools_dir.exists():
        return []
    findings: list[Finding] = []
    for child in sorted(tools_dir.iterdir(), key=lambda path: path.name.lower()):
        if child.name in EXCLUDED_DIRS:
            continue
        if child.is_file() and child.name == "README.md":
            continue
        if child.is_dir() and child.name not in ALLOWED_TOOLS_DIRS:
            findings.append(
                Finding(
                    "tools_dir",
                    str(child.relative_to(root)),
                    "unexpected tools subdirectory; assign it to a runtime lane or document it",
                )
            )
        elif child.is_file() and not child.name.startswith("check_"):
            findings.append(
                Finding(
                    "tools_file",
                    str(child.relative_to(root)),
                    "top-level tools files should be repo checks; lane tools belong in a tools/<lane>/ directory",
                )
            )
    return findings


def iter_source_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for current_root, dir_names, file_names in os.walk(root):
        dir_names[:] = sorted(name for name in dir_names if name not in EXCLUDED_DIRS)
        current = Path(current_root)
        for file_name in sorted(file_names):
            path = current / file_name
            if path.suffix.lower() not in {".py", ".md", ".json", ".yml", ".yaml"}:
                continue
            files.append(path)
    return files


def print_findings(findings: list[Finding]) -> None:
    if not findings:
        print("Project hygiene: no warnings found.")
        return
    print("Project hygiene warnings:")
    for finding in findings:
        print(f"  [{finding.code}] {finding.path}: {finding.message}")


def main() -> int:
    args = parse_args()
    findings = check_project(args.root)
    print_findings(findings)
    return 1 if findings and args.fail_on == "warn" else 0


if __name__ == "__main__":
    raise SystemExit(main())
