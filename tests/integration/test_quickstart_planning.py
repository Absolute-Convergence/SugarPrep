from __future__ import annotations

from pathlib import Path

from sugarprep.domain import DatasetRef
from sugarprep.infrastructure import CsvProfilingPayloadInput
from sugarprep.planning import compile_recipe, parse_recipe
from sugarprep.profiling import DatasetProfiler


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_quickstart_profiles_and_compiles_through_new_boundaries() -> None:
    data_path = PROJECT_ROOT / "examples" / "quickstart" / "data.csv"
    recipe_path = PROJECT_ROOT / "examples" / "quickstart" / "recipe.yaml"
    profile = DatasetProfiler(CsvProfilingPayloadInput()).profile(
        DatasetRef(dataset_id="quickstart-ohlcv", storage_locator=str(data_path))
    )
    recipe = parse_recipe(recipe_path.read_text(encoding="utf-8"))

    plan = compile_recipe(recipe, profile)

    assert plan.recipe_name == "quickstart_ohlcv"
    assert plan.input_snapshot.headers == ("Date", "Open", "High", "Low", "Close", "Volume")
    assert plan.layout.primary_value_column == "close"
