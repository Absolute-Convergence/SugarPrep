from pathlib import Path

import pytest

from sugarprep.infrastructure import TransformersPiiProvider, TransformersPiiProviderError


def test_pii_model_adapter_is_lazy(tmp_path: Path) -> None:
    provider = TransformersPiiProvider(provider_id="pii", model_path=tmp_path / "missing-model")

    with pytest.raises(TransformersPiiProviderError, match="does not exist"):
        provider.detect("text")
