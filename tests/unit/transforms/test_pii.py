from __future__ import annotations

from sugarprep.transforms import detect_pii, mask_text


def test_deterministic_masking_reports_final_non_overlapping_findings() -> None:
    source = "Email ada@example.com, call (312) 555-0199, token=secret-value"

    masked = mask_text(source)

    assert masked.value == "Email [masked email], call [masked phone], [masked token]"
    assert masked.findings == (("email", 1), ("phone", 1), ("token", 1))
    assert detect_pii(masked.value) == ()


def test_non_pii_text_is_unchanged() -> None:
    masked = mask_text("ordinary public value")

    assert masked.value == "ordinary public value"
    assert masked.findings == ()
