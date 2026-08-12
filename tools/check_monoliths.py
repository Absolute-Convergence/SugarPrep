"""Warn when SugarPrep source files grow into likely monoliths.

This sentinel is intentionally warning-oriented. A warning is not a request to
game the number; it is a prompt to review separation of concerns before adding
more behavior to the same file.
"""

from __future__ import annotations

import argparse
import fnmatch
import os
from dataclasses import dataclass
from pathlib import Path


DEFAULT_EXCLUDE_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "DataSets",
    "legacy_reference",
    "models",
    "out",
    "reports",
    "_migration",
    "deployment",
    "manifests",
    "third_party",
    "unsloth_compiled_cache",
}

DEFAULT_EXCLUDE_FILE_PATTERNS = {
    "*.csv",
    "*.parquet",
    "*.pyc",
    "*.zip",
    "*.exe",
    "*.png",
    "*.jpg",
    "*.jpeg",
    "*.gif",
    "*.pdf",
    "*.ipynb",
}

DEFAULT_EXCLUDE_PATHS: set[Path] = set()

SOURCE_EXTENSIONS = {
    ".py",
    ".md",
    ".json",
    ".toml",
    ".yaml",
    ".yml",
    ".ps1",
    ".sh",
}


@dataclass(frozen=True)
class Thresholds:
    warn_lines: int
    high_lines: int
    warn_bytes: int
    high_bytes: int


@dataclass(frozen=True)
class Finding:
    path: Path
    lines: int
    bytes: int
    severity: str
    reasons: tuple[str, ...]


DEFAULT_THRESHOLDS = Thresholds(
    warn_lines=1000,
    high_lines=1500,
    warn_bytes=100_000,
    high_bytes=150_000,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Warn when source files exceed monolith thresholds. "
            "Generated data, models, reports, builds, legacy reference, and SugarBot CLI assets "
            "are excluded by default."
        )
    )
    parser.add_argument("--root", type=Path, default=Path.cwd(), help="Repository root to scan.")
    parser.add_argument("--warn-lines", type=int, default=DEFAULT_THRESHOLDS.warn_lines)
    parser.add_argument("--high-lines", type=int, default=DEFAULT_THRESHOLDS.high_lines)
    parser.add_argument("--warn-bytes", type=int, default=DEFAULT_THRESHOLDS.warn_bytes)
    parser.add_argument("--high-bytes", type=int, default=DEFAULT_THRESHOLDS.high_bytes)
    parser.add_argument(
        "--fail-on",
        choices=["none", "warn", "high"],
        default="none",
        help="Exit nonzero on findings at this severity or above.",
    )
    return parser.parse_args()


def is_excluded_file(path: Path) -> bool:
    name = path.name
    return any(fnmatch.fnmatch(name, pattern) for pattern in DEFAULT_EXCLUDE_FILE_PATTERNS)


def iter_source_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for current_root, dir_names, file_names in os.walk(root):
        current = Path(current_root)
        dir_names[:] = sorted(
            name
            for name in dir_names
            if name not in DEFAULT_EXCLUDE_DIRS
            and (current / name).relative_to(root) not in DEFAULT_EXCLUDE_PATHS
        )
        for file_name in sorted(file_names):
            path = current / file_name
            if is_excluded_file(path):
                continue
            if path.suffix not in SOURCE_EXTENSIONS:
                continue
            files.append(path)
    return files


def count_lines(path: Path) -> int:
    with path.open("rb") as file:
        if path.stat().st_size == 0:
            return 0
        return sum(1 for _ in file)


def classify(path: Path, thresholds: Thresholds) -> Finding | None:
    size = path.stat().st_size
    lines = count_lines(path)
    severity = ""
    reasons: list[str] = []

    if lines >= thresholds.high_lines:
        severity = "HIGH"
        reasons.append(f"lines={lines} >= high_lines={thresholds.high_lines}")
    elif lines >= thresholds.warn_lines:
        severity = "WARN"
        reasons.append(f"lines={lines} >= warn_lines={thresholds.warn_lines}")

    if size >= thresholds.high_bytes:
        severity = "HIGH"
        reasons.append(f"bytes={size} >= high_bytes={thresholds.high_bytes}")
    elif size >= thresholds.warn_bytes:
        severity = "WARN" if severity != "HIGH" else severity
        reasons.append(f"bytes={size} >= warn_bytes={thresholds.warn_bytes}")

    if not severity:
        return None
    return Finding(path=path, lines=lines, bytes=size, severity=severity, reasons=tuple(reasons))


def sort_findings(findings: list[Finding]) -> list[Finding]:
    severity_rank = {"HIGH": 0, "WARN": 1}
    return sorted(findings, key=lambda item: (severity_rank[item.severity], -item.lines, -item.bytes, str(item.path)))


def print_findings(root: Path, findings: list[Finding]) -> None:
    if not findings:
        print("Monolith sentinel: no oversized source files found.")
        return

    print("Monolith sentinel warnings:")
    print("  These are design-review signals, not numbers to game.")
    for finding in sort_findings(findings):
        rel_path = finding.path.relative_to(root)
        reason = "; ".join(finding.reasons)
        print(f"  [{finding.severity}] {rel_path} ({reason})")


def exit_code(findings: list[Finding], fail_on: str) -> int:
    if fail_on == "none" or not findings:
        return 0
    if fail_on == "warn":
        return 1
    return 1 if any(finding.severity == "HIGH" for finding in findings) else 0


def main() -> int:
    args = parse_args()
    root = args.root.resolve()
    thresholds = Thresholds(
        warn_lines=args.warn_lines,
        high_lines=args.high_lines,
        warn_bytes=args.warn_bytes,
        high_bytes=args.high_bytes,
    )
    findings = [finding for path in iter_source_files(root) if (finding := classify(path, thresholds)) is not None]
    print_findings(root, findings)
    return exit_code(findings, args.fail_on)


if __name__ == "__main__":
    raise SystemExit(main())
