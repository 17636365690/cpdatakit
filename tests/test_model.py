from __future__ import annotations

from pathlib import Path

import pandas as pd

from cpdatakit.model import Dataset


def test_dataset_copy_isolates_nested_metadata_and_data() -> None:
    original = Dataset(
        pd.DataFrame({"value": [1.0]}),
        {"nested": {"labels": ["raw"]}},
        Path("input.csv"),
    )

    copied = original.copy()
    copied.metadata["nested"]["labels"].append("normalized")
    copied.data.loc[0, "value"] = 2.0

    assert original.metadata == {"nested": {"labels": ["raw"]}}
    assert original.data["value"].tolist() == [1.0]
    assert copied.source == original.source
