from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from sugarprep.domain import DatasetRef
from sugarprep.inference import (
    CLEANER_TOOL_NAMES,
    CleanerInferenceService,
    CleanerPlannedToolCall,
    CleanerToolPlan,
)
from sugarprep.infrastructure import (
    CsvCleanerCandidateOutput,
    CsvCleanerPayloadInput,
    CsvPayloadError,
)
from sugarprep.infrastructure.filesystem import resolve_local_file
from sugarprep.transforms import CleanerExecutionError, CleanerExecutionPipeline


class _StaticCleanerProvider:
    provider_id = "qwen-cleaner-test"

    def __init__(self, plan: CleanerToolPlan) -> None:
        self._response = json.dumps(plan.to_dict())

    def generate(self, _request: dict[str, Any]) -> str:
        return self._response


def _source(tmp_path: Path, text: str, *, name: str = "source.csv") -> tuple[Path, CsvCleanerPayloadInput]:
    path = tmp_path / name
    path.write_bytes(text.encode("utf-8"))
    return path, CsvCleanerPayloadInput()


def _candidate(plan: CleanerToolPlan, source: Path, source_sha256: str):
    return CleanerInferenceService(_StaticCleanerProvider(plan)).propose(
        context={"schema_version": "sugarprep.cleaner_curriculum_context.v1"},
        source_sha256=source_sha256,
        case_id=plan.plan_id,
        source_csv=source,
    )


def _execute(tmp_path: Path, source: Path, payload: CsvCleanerPayloadInput, plan: CleanerToolPlan):
    snapshot = payload.inspect(
        DatasetRef(dataset_id=plan.plan_id, storage_locator=source.as_uri())
    )
    candidate = _candidate(plan, source, snapshot.content_sha256)
    result = CleanerExecutionPipeline(
        payload,
        CsvCleanerCandidateOutput(tmp_path / "candidates"),
    ).execute(input_snapshot=snapshot, candidate=candidate)
    return snapshot, candidate, result


def _plan(
    plan_id: str,
    calls: list[tuple[str, dict[str, Any]]],
) -> CleanerToolPlan:
    planned: list[CleanerPlannedToolCall] = []
    previous: str | None = None
    for index, (tool_name, arguments) in enumerate(calls, start=1):
        call_id = f"step-{index:02d}"
        planned.append(
            CleanerPlannedToolCall(
                call_id=call_id,
                tool_name=tool_name,
                arguments=arguments,
                purpose=f"Exercise deterministic {tool_name}.",
                preconditions=(() if previous is None else (previous,)),
            )
        )
        previous = call_id
    return CleanerToolPlan(
        plan_id=plan_id,
        stop_reason="execute",
        tool_calls=tuple(planned),
    )


def _output_bytes(result) -> bytes:
    assert result.output_snapshot is not None
    return resolve_local_file(result.output_snapshot.reference).read_bytes()


def test_retained_execute_specimen_is_exact_source_bound_and_original_preserving(
    tmp_path: Path,
) -> None:
    specimen = json.loads(
        Path("tests/fixtures/model_parity/cleaner.json").read_text(encoding="utf-8")
    )
    case = specimen["cases"][0]
    source, payload = _source(tmp_path, case["source_csv"])
    source_before = source.read_bytes()
    plan = CleanerToolPlan.from_dict(case["response"])

    snapshot, candidate, result = _execute(tmp_path, source, payload, plan)

    assert snapshot.content_sha256 == case["source_sha256"]
    assert _output_bytes(result) == case["expected_output_csv"].encode("utf-8")
    assert source.read_bytes() == source_before
    assert result.plan_candidate_id == candidate.candidate_id
    assert result.evidence is not None
    assert result.evidence.input_sha256 == snapshot.content_sha256
    assert result.evidence.output_sha256 == result.output_snapshot.content_sha256
    assert result.output_snapshot.provenance.operation == "cleaner:baseline-plan"
    assert result.output_snapshot.provenance.cleaner_evidence is result.evidence
    assert result.metadata == {"model": "qwen35-4b-cleaner-sft-v1-full"}
    assert [item.tool_name for item in result.evidence.tool_executions] == [
        "detect_file_format",
        "normalize_column_names",
        "validate_parseable_table",
        "validate_parseable_table",
    ]
    assert result.evidence.tool_executions[1].arguments == {
        "header_mapping": ["Date", "close", "volume"]
    }
    assert result.evidence.tool_executions[-1].call_id == "cleaner-authoritative-validation"


def test_header_trim_cell_parsing_and_deduplication_compose_deterministically(
    tmp_path: Path,
) -> None:
    source, payload = _source(
        tmp_path,
        "# generated report\n"
        " Date , Value , Note \n"
        "2026/01/01,\"$1,200\",NA\n"
        "2026/01/01,\"$1,200\",NA\n"
        "2026-01-02,2K,ok\n"
        "footer\n",
    )
    plan = _plan(
        "cleaner-structural-values",
        [
            ("detect_file_format", {}),
            ("select_header_row", {"header_line_number": 2}),
            ("trim_preamble_footer", {"header_line_number": 2}),
            ("normalize_column_names", {}),
            ("normalize_missing_tokens", {"columns": ["Note"], "missing_tokens": ["NA"]}),
            (
                "parse_datetime",
                {
                    "columns": ["Date"],
                    "params": {
                        "formats": ["%Y/%m/%d", "%Y-%m-%d"],
                        "output_format": "%Y-%m-%d",
                    },
                },
            ),
            ("parse_flexible_number", {"columns": ["Value"]}),
            ("deduplicate_rows", {"key_columns": ["Date", "Value"]}),
            ("validate_parseable_table", {}),
        ],
    )

    _snapshot, _candidate_value, result = _execute(tmp_path, source, payload, plan)

    assert _output_bytes(result) == (
        b"Date,Value,Note\n"
        b"2026-01-01,1200,\n"
        b"2026-01-02,2000,ok\n"
    )
    assert result.evidence is not None
    assert result.evidence.rows_quarantined == 3
    assert result.evidence.tool_executions[2].details["quarantine_reason_counts"] == {
        "preamble": 1,
        "field_count_mismatch": 1,
    }


def test_ragged_row_repair_is_conservative_and_records_quarantine(tmp_path: Path) -> None:
    source, payload = _source(
        tmp_path,
        "a,b,c\n"
        "1,2\n"
        "3,4,5,,\n"
        "6,7,8,9\n",
    )
    plan = _plan(
        "cleaner-ragged",
        [
            ("detect_file_format", {}),
            ("repair_ragged_rows", {}),
            ("validate_parseable_table", {}),
        ],
    )

    _snapshot, _candidate_value, result = _execute(tmp_path, source, payload, plan)

    assert _output_bytes(result) == b"a,b,c\n1,2,\n3,4,5\n"
    assert result.evidence is not None
    repair = result.evidence.tool_executions[1]
    assert repair.rows_input == 3
    assert repair.rows_output == 2
    assert repair.rows_quarantined == 1
    assert repair.details["repair_reason_counts"] == {
        "padded_short_row": 1,
        "trimmed_trailing_empty_fields": 1,
    }


def test_multirow_header_flattening_is_copy_producing(tmp_path: Path) -> None:
    source, payload = _source(
        tmp_path,
        "Date,Price,Price\n"
        ",Open,Close\n"
        "2026-01-01,10,11\n",
    )
    source_before = source.read_bytes()
    plan = _plan(
        "cleaner-flatten",
        [
            ("flatten_multirow_header", {"header_row_count": 2, "separator": "_"}),
            ("validate_parseable_table", {}),
        ],
    )

    _snapshot, _candidate_value, result = _execute(tmp_path, source, payload, plan)

    assert _output_bytes(result) == b"Date,Price_Open,Price_Close\n2026-01-01,10,11\n"
    assert source.read_bytes() == source_before


def test_split_and_datetime_join_quarantine_only_unsafe_rows(tmp_path: Path) -> None:
    source, payload = _source(
        tmp_path,
        "compound,year,month,day,value\n"
        "BTC|daily,2026,1,2,10\n"
        "BROKEN,2026,1,2,11\n"
        "ETH|daily,2026,13,2,12\n",
    )
    plan = _plan(
        "cleaner-derived-columns",
        [
            (
                "split_compound_column",
                {
                    "source_column": "compound",
                    "delimiter": "|",
                    "output_columns": ["symbol", "frequency"],
                },
            ),
            (
                "join_datetime_parts",
                {
                    "output_column": "event_date",
                    "params": {
                        "year": "year",
                        "month": "month",
                        "day": "day",
                        "output_format": "%Y-%m-%d",
                    },
                },
            ),
            ("validate_parseable_table", {}),
        ],
    )

    _snapshot, _candidate_value, result = _execute(tmp_path, source, payload, plan)

    assert _output_bytes(result) == (
        b"compound,year,month,day,value,symbol,frequency,event_date\n"
        b"BTC|daily,2026,1,2,10,BTC,daily,2026-01-02\n"
    )
    assert result.evidence is not None
    assert result.evidence.rows_quarantined == 2
    assert result.evidence.tool_executions[0].rows_quarantined == 1
    assert result.evidence.tool_executions[1].rows_quarantined == 1


def test_wide_period_normalization_preserves_skips_as_nonrow_evidence(tmp_path: Path) -> None:
    source, payload = _source(
        tmp_path,
        "series,region,2026-01,2026-Q2,2027\n"
        "alpha,US,1,NA,3\n"
        "beta,EU,bad,4,5\n",
    )
    plan = _plan(
        "cleaner-wide-periods",
        [
            ("normalize_wide_periods", {"missing_tokens": ["NA"]}),
            ("validate_parseable_table", {}),
        ],
    )

    _snapshot, _candidate_value, result = _execute(tmp_path, source, payload, plan)

    assert _output_bytes(result) == (
        b"series_id,period_start,period_label,period_kind,period_year,period_month,"
        b"period_quarter,value,series,region\n"
        b"alpha,2026-01-01,2026-01,month,2026,1,,1,alpha,US\n"
        b"alpha,2027-01-01,2027,year,2027,,,3,alpha,US\n"
        b"beta,2026-04-01,2026-Q2,quarter,2026,,2,4,beta,EU\n"
        b"beta,2027-01-01,2027,year,2027,,,5,beta,EU\n"
    )
    assert result.evidence is not None
    wide = result.evidence.tool_executions[0]
    assert wide.rows_quarantined == 0
    assert wide.details["values_skipped"] == 2
    assert result.evidence.rows_quarantined == 0


@pytest.mark.parametrize(
    ("stop_reason", "unknowns", "diagnostics"),
    [
        ("needs_user_input", ("Select the intended header.",), {}),
        ("cannot_repair", (), {"reason_code": "corrupt_quoting"}),
    ],
)
def test_stop_outcomes_do_not_read_write_or_validate_a_candidate_copy(
    tmp_path: Path,
    stop_reason: str,
    unknowns: tuple[str, ...],
    diagnostics: dict[str, str],
) -> None:
    source, payload = _source(tmp_path, "a,b\n1,2\n")
    snapshot = payload.inspect(DatasetRef(dataset_id="stop", storage_locator=source.as_uri()))
    plan = CleanerToolPlan(
        plan_id="cleaner-needs-input",
        stop_reason=stop_reason,
        unknowns=unknowns,
        warnings=("retained warning",),
        diagnostics=diagnostics,
        metadata={"case": "retained-stop"},
    )
    candidate = _candidate(plan, source, snapshot.content_sha256)
    candidate_root = tmp_path / "candidates"

    result = CleanerExecutionPipeline(
        payload,
        CsvCleanerCandidateOutput(candidate_root),
    ).execute(input_snapshot=snapshot, candidate=candidate)

    assert result.stop_reason == stop_reason
    assert result.output_snapshot is None
    assert result.evidence is None
    assert result.unknowns == unknowns
    assert result.warnings == ("retained warning",)
    assert result.diagnostics == diagnostics
    assert result.metadata == {"case": "retained-stop"}
    assert not candidate_root.exists()


def test_execution_rejects_source_mismatch_and_changed_source(tmp_path: Path) -> None:
    source, payload = _source(tmp_path, "a,b\n1,2\n")
    snapshot = payload.inspect(DatasetRef(dataset_id="bound", storage_locator=source.as_uri()))
    plan = _plan("cleaner-source-bound", [("validate_parseable_table", {})])
    candidate = _candidate(plan, source, snapshot.content_sha256)
    pipeline = CleanerExecutionPipeline(
        payload,
        CsvCleanerCandidateOutput(tmp_path / "candidates"),
    )

    other, other_payload = _source(tmp_path, "a,b\n9,9\n", name="other.csv")
    other_snapshot = other_payload.inspect(
        DatasetRef(dataset_id="other", storage_locator=other.as_uri())
    )
    with pytest.raises(CleanerExecutionError, match="does not match"):
        pipeline.execute(input_snapshot=other_snapshot, candidate=candidate)

    source.write_bytes(b"a,b\n3,4\n")
    with pytest.raises(CsvPayloadError, match="changed"):
        pipeline.execute(input_snapshot=snapshot, candidate=candidate)


def test_behavioral_cases_cover_every_retained_cleaner_tool() -> None:
    exercised = {
        "detect_file_format",
        "select_header_row",
        "flatten_multirow_header",
        "trim_preamble_footer",
        "repair_ragged_rows",
        "normalize_column_names",
        "normalize_missing_tokens",
        "parse_flexible_number",
        "parse_datetime",
        "join_datetime_parts",
        "normalize_wide_periods",
        "split_compound_column",
        "deduplicate_rows",
        "validate_parseable_table",
    }

    assert exercised == CLEANER_TOOL_NAMES
