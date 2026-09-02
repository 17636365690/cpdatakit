from __future__ import annotations

import json
from pathlib import Path

from cpdatakit.application import (
    CapabilityRequest,
    ServiceResult,
    discover_capabilities,
)


def test_capability_discovery_returns_deterministic_builtin_and_optional_items() -> None:
    result = discover_capabilities(CapabilityRequest())

    assert isinstance(result, ServiceResult)
    assert result.ok
    assert result.value is not None
    items = result.value.items
    identities = [(item.kind, item.name) for item in items]
    assert identities == sorted(identities)
    assert len(identities) == len(set(identities))
    assert ("reader", "csv") in identities
    assert ("writer", "hdf5-v2") in identities
    assert ("reader", "netcdf:h5netcdf") in identities
    assert ("writer", "zarr-v3") in identities
    assert ("plot", "stress-strain") in identities
    assert all(item.name and item.format_name for item in items)


def test_capability_discovery_keeps_unavailable_dependencies_explicit() -> None:
    result = discover_capabilities(CapabilityRequest(include_unavailable=True))

    assert result.ok
    assert result.value is not None
    ui = next(item for item in result.value.items if item.name == "local-ui")
    assert isinstance(ui.available, bool)
    if not ui.available:
        assert ui.reason
        assert "missing" in ui.reason


def test_capability_discovery_safe_mode_excludes_registered_external_adapters() -> None:
    normal = discover_capabilities(CapabilityRequest())
    safe = discover_capabilities(CapabilityRequest(safe_mode=True))

    assert normal.ok and safe.ok
    assert normal.value is not None and safe.value is not None
    assert any(item.kind == "adapter" for item in normal.value.items)
    assert not any(item.kind == "adapter" for item in safe.value.items)


def test_capability_discovery_result_is_json_safe_without_workspace_paths() -> None:
    result = discover_capabilities(CapabilityRequest())

    assert result.ok
    rendered = json.dumps(result.to_dict(), allow_nan=False)
    assert "C:\\" not in rendered
    assert "/Users/" not in rendered
    assert Path.cwd().as_posix() not in rendered
