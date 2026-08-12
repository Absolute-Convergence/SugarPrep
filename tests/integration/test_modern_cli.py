from __future__ import annotations

import json
from pathlib import Path

from sugarprep.cli import main


def _source(tmp_path: Path, volume: str = "1.2K") -> Path:
    source = tmp_path / "ohlcv.csv"
    source.write_text(
        "Date,Open,High,Low,Close,Volume\n"
        f"20260808,$10.00,$12.00,$9.00,$11.00,{volume}\n",
        encoding="utf-8",
    )
    return source


def test_profile_and_validate_commands_emit_path_free_json(tmp_path: Path, capsys) -> None:
    source = _source(tmp_path)

    assert main(["profile", str(source)]) == 0
    profile_payload = json.loads(capsys.readouterr().out)
    assert profile_payload["dataset_id"] == "ohlcv"
    assert profile_payload["headers"] == ["Date", "Open", "High", "Low", "Close", "Volume"]

    assert main(["validate", str(source)]) == 0
    validation_output = capsys.readouterr().out
    validation_payload = json.loads(validation_output)
    assert validation_payload["passed"] is True
    assert str(tmp_path) not in validation_output


def test_prepare_requires_explicit_acceptance_before_bundle_commit(tmp_path: Path, capsys) -> None:
    source = _source(tmp_path)
    output_root = tmp_path / "output"
    recipe = Path("examples/quickstart/recipe.yaml")

    assert (
        main(
            [
                "prepare",
                str(source),
                "--recipe",
                str(recipe),
                "--output-root",
                str(output_root),
            ]
        )
        == 0
    )
    review_payload = json.loads(capsys.readouterr().out)
    assert review_payload["status"] == "ready_for_acceptance"
    assert not (output_root / "bundles").exists()

    assert (
        main(
            [
                "prepare",
                str(source),
                "--recipe",
                str(recipe),
                "--output-root",
                str(output_root),
                "--accept-by",
                "cli-test",
            ]
        )
        == 0
    )
    accepted_payload = json.loads(capsys.readouterr().out)
    assert accepted_payload["status"] == "accepted"
    assert accepted_payload["bundle_id"].startswith("bundle-")
    assert len(list((output_root / "bundles").iterdir())) == 1


def test_prepare_validation_failure_commits_no_bundle(tmp_path: Path, capsys) -> None:
    source = _source(tmp_path, volume="-1")
    output_root = tmp_path / "output"

    exit_code = main(
        [
            "prepare",
            str(source),
            "--recipe",
            "examples/quickstart/recipe.yaml",
            "--output-root",
            str(output_root),
            "--accept-by",
            "cli-test",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert payload["status"] == "validation_failed"
    assert not (output_root / "bundles").exists()
    assert list((output_root / "candidates").iterdir()) == []
