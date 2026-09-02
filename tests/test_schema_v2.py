from __future__ import annotations

import json
from pathlib import Path

import pytest

from cpdatakit.schemas import (
    SchemaV2Error,
    resolve_schema_v2,
    schema_v2_canonical_json,
    schema_v2_sha256,
)

ROOT = Path(__file__).parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "schema-v2"


def test_schema_v2_resolves_composition_in_manifest_and_declaration_order() -> None:
    result = resolve_schema_v2(FIXTURES / "composed.json")
    expected = json.loads((FIXTURES / "expected-resolved.json").read_text(encoding="utf-8"))

    assert result.to_dict() == expected
    assert result.source_manifest == (
        "base.json",
        "fragment-space.json",
        "fragment-temperature.json",
    )
    assert result.resolved_order == ("time", "y", "x", "stage", "temperature")
    assert (
        schema_v2_sha256(result)
        == "65e820c6f5ed729e47e52b6a6592fb56352644a635e547c5ffde88014c431619"
    )


def test_schema_v2_canonical_json_is_stable_for_the_resolved_contract() -> None:
    result = resolve_schema_v2(FIXTURES / "composed.json")

    assert schema_v2_canonical_json(result) == schema_v2_canonical_json(result)
    assert '"schema_version":"2.0"' in schema_v2_canonical_json(result)


def test_schema_v2_resolves_standalone_source_without_composition() -> None:
    result = resolve_schema_v2(FIXTURES / "standalone.json")

    assert result.schema.profile == "thermal-field"
    assert [item.name for item in result.schema.dimensions] == ["time", "y", "x"]
    assert result.source_manifest == ("standalone.json",)


def test_schema_v2_rejects_cycle_and_duplicate_declarations() -> None:
    with pytest.raises(SchemaV2Error, match="extends cycle"):
        resolve_schema_v2(FIXTURES / "invalid-cycle.json")
    with pytest.raises(SchemaV2Error, match="duplicate variable declaration"):
        resolve_schema_v2(FIXTURES / "invalid-collision.json")


def test_schema_v2_rejects_missing_and_remote_sources(tmp_path: Path) -> None:
    missing = tmp_path / "missing.json"
    missing.write_text(
        json.dumps(
            {
                "profile": "missing",
                "schema_version": "2.0",
                "extends": "does-not-exist.json",
            }
        ),
        encoding="utf-8",
    )
    remote = tmp_path / "remote.json"
    remote.write_text(
        json.dumps(
            {
                "profile": "remote",
                "schema_version": "2.0",
                "extends": "https://example.invalid/schema.json",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(SchemaV2Error, match="does not exist"):
        resolve_schema_v2(missing)
    with pytest.raises(SchemaV2Error, match="HTTP"):
        resolve_schema_v2(remote)


def test_schema_v2_rejects_incompatible_declaration_override(tmp_path: Path) -> None:
    base = tmp_path / "base.json"
    base.write_text(
        json.dumps(
            {
                "profile": "override",
                "schema_version": "2.0",
                "dimensions": [{"name": "time", "length": 2}],
                "coordinates": [],
                "variables": [
                    {
                        "name": "temperature",
                        "dims": ["time"],
                        "dtype": "float",
                        "unit": "K",
                        "role": "measured_field",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    derived = tmp_path / "derived.json"
    derived.write_text(
        json.dumps(
            {
                "profile": "override",
                "schema_version": "2.0",
                "extends": "base.json",
                "dimensions": [],
                "coordinates": [],
                "variables": [
                    {
                        "name": "temperature",
                        "dims": ["time"],
                        "dtype": "float",
                        "unit": "C",
                        "role": "measured_field",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(SchemaV2Error, match="incompatible variable override"):
        resolve_schema_v2(derived)
