from __future__ import annotations

from pathlib import Path
from urllib.parse import unquote, urlparse
from urllib.request import url2pathname

from sugarprep.domain import DatasetRef
from sugarprep.infrastructure import (
    CsvProfilingPayloadInput,
    CsvTransformCandidateOutput,
    CsvTransformPayloadInput,
)
from sugarprep.planning import compile_recipe, parse_recipe
from sugarprep.profiling import DatasetProfiler
from sugarprep.transforms import TransformPipeline


def test_quickstart_recipe_profiles_compiles_and_writes_candidate_copy(tmp_path: Path) -> None:
    source = tmp_path / "ohlcv.csv"
    source.write_text(
        "Date,Open,High,Low,Close,Volume\n"
        "20260808,$10.00,$12.00,$9.00,$11.00,1.2K\n"
        "20260809,$11.00,$13.00,$10.00,$12.00,2K\n",
        encoding="utf-8",
    )
    reference = DatasetRef(dataset_id="quickstart", storage_locator=source.as_uri())
    profile = DatasetProfiler(CsvProfilingPayloadInput()).profile(reference)
    recipe = parse_recipe(Path("examples/quickstart/recipe.yaml").read_text(encoding="utf-8"))
    plan = compile_recipe(recipe, profile)

    result = TransformPipeline(
        CsvTransformPayloadInput(),
        CsvTransformCandidateOutput(tmp_path / "candidates"),
    ).execute(plan)

    assert result.completed
    assert not result.has_errors
    assert result.output_snapshot is not None
    assert result.output_snapshot.reference != reference
    assert result.output_snapshot.provenance.parent_sha256 == (profile.snapshot.content_sha256,)
    parsed = urlparse(result.output_snapshot.reference.storage_locator)
    candidate_path = Path(url2pathname(unquote(parsed.path.lstrip("/"))))
    assert candidate_path != source
    assert source.read_text(encoding="utf-8").startswith("Date,Open")
    assert result.output_snapshot.row_count == 2
