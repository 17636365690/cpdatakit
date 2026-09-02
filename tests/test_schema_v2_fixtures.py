from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "schema-v2"


def _load(name: str) -> dict[str, object]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_schema_v2_fixtures_declare_local_composition_and_resolved_order() -> None:
    names = [
        "standalone.json",
        "base.json",
        "fragment-space.json",
        "fragment-temperature.json",
        "composed.json",
        "expected-resolved.json",
        "invalid-cycle.json",
        "invalid-collision.json",
    ]
    for name in names:
        payload = _load(name)
        assert payload["schema_version"] == "2.0"
        assert payload["profile"]

    composed = _load("composed.json")
    assert composed["extends"] == "base.json"
    assert composed["includes"] == ["fragment-space.json", "fragment-temperature.json"]
    resolved = _load("expected-resolved.json")
    assert resolved["resolved_order"] == [
        "time",
        "y",
        "x",
        "stage",
        "temperature",
    ]
    assert resolved["source_manifest"] == [
        "base.json",
        "fragment-space.json",
        "fragment-temperature.json",
    ]


def test_schema_v2_expected_resolved_json_has_stable_hash() -> None:
    resolved = _load("expected-resolved.json")
    canonical = json.dumps(
        resolved["resolved"], ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )

    assert (
        hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        == "65e820c6f5ed729e47e52b6a6592fb56352644a635e547c5ffde88014c431619"
    )


def test_schema_v2_invalid_fixtures_name_the_failure() -> None:
    assert _load("invalid-cycle.json")["reason"] == "extends cycle"
    assert _load("invalid-collision.json")["reason"] == "duplicate variable declaration"
