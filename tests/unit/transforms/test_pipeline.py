from __future__ import annotations

from collections.abc import Iterable

from sugarprep.domain import (
    DatasetProvenance,
    DatasetRef,
    DatasetSnapshot,
    Layout,
    OutputColumn,
    PreparationPlan,
    RowRule,
    TransformSpec,
)
from sugarprep.transforms import TransformPipeline


def _snapshot(dataset_id: str = "source") -> DatasetSnapshot:
    return DatasetSnapshot(
        reference=DatasetRef(dataset_id=dataset_id, storage_locator="opaque://payload"),
        content_sha256="a" * 64,
        media_type="text/csv",
        headers=("date", "amount"),
        row_count=2,
    )


def _plan(*, reject_policy: str = "fail", rule_action: str = "reject") -> PreparationPlan:
    return PreparationPlan(
        plan_id="plan-test",
        version=1,
        recipe_name="test",
        input_snapshot=_snapshot(),
        output_columns=(
            OutputColumn(name="row_index", generate="row_index"),
            OutputColumn(name="date", source="date", transforms=(TransformSpec(name="trim"),)),
            OutputColumn(
                name="amount",
                source="amount",
                transforms=(TransformSpec(name="parse_flexible_number"),),
            ),
        ),
        layout=Layout(
            time_column="date",
            time_kind="YYYY-MM-DD",
            value_columns=("amount",),
            primary_value_column="amount",
        ),
        row_rules=(RowRule(name="nonnegative", column="amount", action=rule_action),),
        reject_policy=reject_policy,
    )


class FakeInput:
    def __init__(self, rows: tuple[tuple[str, ...], ...]) -> None:
        self.rows = rows
        self.assertions = 0

    def iter_rows(self, _snapshot: DatasetSnapshot) -> Iterable[tuple[str, ...]]:
        return iter(self.rows)

    def assert_unchanged(self, _snapshot: DatasetSnapshot) -> None:
        self.assertions += 1


class FakeOutput:
    def __init__(self) -> None:
        self.rows: tuple[tuple[str, ...], ...] | None = None
        self._buffer: list[tuple[str, ...]] = []

    def open_candidate(
        self,
        *,
        input_snapshot: DatasetSnapshot,
        plan_id: str,
        headers: tuple[str, ...],
    ) -> FakeOutput:
        self._input_snapshot = input_snapshot
        self._plan_id = plan_id
        self._headers = headers
        return self

    def write_row(self, row: tuple[str, ...]) -> None:
        self._buffer.append(row)

    def commit(self) -> DatasetSnapshot:
        self.rows = tuple(self._buffer)
        return DatasetSnapshot(
            reference=DatasetRef(dataset_id="candidate", storage_locator="opaque://candidate"),
            content_sha256="b" * 64,
            media_type="text/csv",
            headers=self._headers,
            row_count=len(self.rows),
            provenance=DatasetProvenance(
                operation=f"prepare:{self._plan_id}",
                parent_sha256=(self._input_snapshot.content_sha256,),
            ),
        )

    def abort(self) -> None:
        self.rows = None
        self._buffer.clear()


def test_pipeline_returns_unwritten_failed_result_when_fail_policy_rejects() -> None:
    payload_input = FakeInput((("2026-08-09", "10"), ("2026-08-10", "-1")))
    candidate_output = FakeOutput()

    result = TransformPipeline(payload_input, candidate_output).execute(_plan())

    assert not result.completed
    assert result.has_errors
    assert result.rejected_rows[0].source_row_number == 2
    assert candidate_output.rows is None
    assert payload_input.assertions == 1


def test_pipeline_drop_policy_writes_candidate_without_rejected_rows() -> None:
    payload_input = FakeInput((("2026-08-09", "$10"), ("2026-08-10", "-1")))
    candidate_output = FakeOutput()

    result = TransformPipeline(payload_input, candidate_output).execute(_plan(reject_policy="drop"))

    assert result.completed
    assert not result.has_errors
    assert result.output_snapshot is not None
    assert result.output_snapshot.row_count == 1
    assert result.rejected_rows[0].source_row_number == 2
    assert candidate_output.rows == (("1", "2026-08-09", "10"),)
    assert payload_input.assertions == 2


def test_pipeline_warn_rule_keeps_row_and_records_warning() -> None:
    payload_input = FakeInput((("2026-08-09", "-1"),))
    candidate_output = FakeOutput()

    result = TransformPipeline(payload_input, candidate_output).execute(_plan(rule_action="warn"))

    assert result.completed
    assert candidate_output.rows == (("1", "2026-08-09", "-1"),)
    assert result.warnings == ("source row 1: amount failed nonnegative: -1 is negative",)
