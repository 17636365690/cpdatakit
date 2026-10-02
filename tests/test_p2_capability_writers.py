"""Available writer discovery must describe operations users can run."""

from cpdatakit.application import CapabilityRequest, discover_capabilities


def test_csv_json_are_not_advertised_as_available_data_writers():
    result = discover_capabilities(CapabilityRequest(include_unavailable=True))
    assert result.ok
    readers = {item.name for item in result.value.items if item.kind == "reader" and item.available}
    writers = {item.name for item in result.value.items if item.kind == "writer" and item.available}
    assert {"csv", "json"} <= readers
    assert {"csv", "json"}.isdisjoint(writers)
    assert {"hdf5-v1", "hdf5-v2", "parquet", "zarr-v3"} <= writers
