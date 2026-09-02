from __future__ import annotations

import json
from pathlib import Path

from cpdatakit.io import load_dataset
from cpdatakit.normalization import load_mapping_file, normalize_dataset
from cpdatakit.schema import load_schema

ROOT = Path(__file__).parents[1]
REFERENCE = ROOT / "examples" / "thermal-field-v2"


def test_thermal_field_reference_has_explicit_dimensions_coordinates_and_values() -> None:
    payload = json.loads((REFERENCE / "reference.json").read_text(encoding="utf-8"))

    assert payload["dimensions"] == {"time": 4, "y": 3, "x": 4}
    assert payload["coordinates"]["time"] == {
        "dims": ["time"],
        "unit": "s",
        "values": [0.0, 10.0, 20.0, 30.0],
    }
    assert payload["coordinates"]["x"]["unit"] == "mm"
    assert payload["coordinates"]["y"]["values"] == [-1.0, 0.0, 1.0]
    temperature = payload["variables"]["temperature"]
    assert temperature["dims"] == ["time", "y", "x"]
    assert temperature["unit"] == "K"
    assert temperature["values"][0] == [
        [273.15, 274.15, 275.15, 276.15],
        [275.15, 276.15, 277.15, 278.15],
        [277.15, 278.15, 279.15, 280.15],
    ]
    assert temperature["values"][3][2][3] == 310.15


def test_thermal_field_malformed_cases_explain_lossless_conversion_failures() -> None:
    ambiguous = json.loads(
        (REFERENCE / "malformed" / "ambiguous-record-axis.json").read_text(encoding="utf-8")
    )
    object_array = json.loads(
        (REFERENCE / "malformed" / "object-array.json").read_text(encoding="utf-8")
    )

    assert ambiguous["reason"] == "multiple candidate record dimensions"
    assert object_array["reason"] == "object dtype cannot be represented losslessly"


def test_existing_thermal_cycle_table_is_the_lossless_tabular_case() -> None:
    example = ROOT / "examples" / "thermal-cycle"
    schema = load_schema(example / "schema" / "thermal-cycle.json")
    raw = load_dataset(example / "input" / "thermal-cycle.csv")
    mappings, drop_unmapped = load_mapping_file(example / "mappings" / "thermal-cycle.json")

    normalized = normalize_dataset(raw, schema, mappings, drop_unmapped=drop_unmapped)

    assert list(normalized.data.columns) == ["time", "temperature", "stage"]
    assert normalized.data.shape == (4, 3)
    assert normalized.data["time"].tolist() == [0.0, 600.0, 1200.0, 1800.0]
