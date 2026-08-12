"""SugarPrep command-line parser and composition dispatch."""

from __future__ import annotations

import argparse
import sys
from typing import Sequence

from sugarprep.cli.commands import prepare, profile, validate
from sugarprep.domain.errors import SugarPrepError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sugarprep", description="Deterministic SugarPrep runtime")
    subparsers = parser.add_subparsers(dest="command", required=True)
    command_specs = (
        ("profile", "Profile a CSV dataset", profile.configure),
        ("prepare", "Prepare a candidate copy from an explicit recipe", prepare.configure),
        ("validate", "Validate CSV structure and fingerprint evidence", validate.configure),
    )
    for name, help_text, configure in command_specs:
        command_parser = subparsers.add_parser(name, help=help_text, description=help_text)
        configure(command_parser)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.command_handler(args))
    except (SugarPrepError, OSError, ValueError) as exc:
        print(f"sugarprep: {exc}", file=sys.stderr)
        return 2
