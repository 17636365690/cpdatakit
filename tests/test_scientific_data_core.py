from __future__ import annotations

from pathlib import Path

from cpdatakit.io import load_dataset
from cpdatakit.normalization import load_mapping_file, normalize_dataset
from cpdatakit.schema import load_schema
from cpdatakit.statistics import summarize_dataset
from cpdatakit.validation import validate_dataset

EXAMPLE = Path(__file__).parents[1] / "examples" / "thermal-cycle"


def test_thermal_cycle_example_is_a_valid_non_cp_contract() -> None:
    schema = load_schema(EXAMPLE / "schema" / "thermal-cycle.json")
    dataset = load_dataset(EXAMPLE / "input" / "thermal-cycle.csv")
    mappings, drop_unmapped = load_mapping_file(EXAMPLE / "mappings" / "thermal-cycle.json")

    normalized = normalize_dataset(
        dataset,
        schema,
        mappings,
        drop_unmapped=drop_unmapped,
    )
    validation = validate_dataset(normalized, schema)
    summary = summarize_dataset(normalized, schema, validation=validation)

    assert schema.profile == "thermal-cycle"
    assert validation.valid
    assert normalized.data["time"].tolist() == [0.0, 600.0, 1200.0, 1800.0]
    assert normalized.data["temperature"].tolist() == [298.15, 423.15, 423.15, 298.15]
    assert normalized.data["stage"].tolist() == ["ambient", "heating", "hold", "cooling"]
    assert summary["numeric_fields"]["temperature"]["max"] == 423.15
    assert "unique_grains" not in summary
