"""Detection reports real I/O failures and provenance retains its fixed projection."""

import h5py
import pytest

from cpdatakit.adapters import DamaskDADF5Adapter
from cpdatakit.exceptions import DataReadError
from cpdatakit.inspection import _portable_provenance


def test_damask_detection_preserves_corrupt_file_cause(tmp_path):
    path = tmp_path / "broken.hdf5"
    path.write_bytes(b"corrupted HDF5 payload")
    with pytest.raises(DataReadError) as caught:
        DamaskDADF5Adapter.detect(path)
    assert isinstance(caught.value.__cause__, OSError)
    assert str(caught.value.__cause__) in str(caught.value)
    assert "format marker" not in str(caught.value)


def test_damask_detection_preserves_open_permission_error(tmp_path, monkeypatch):
    path = tmp_path / "unreadable.hdf5"
    failure = PermissionError("permission denied by injected open failure")

    def denied(*args, **kwargs):
        raise failure

    monkeypatch.setattr(h5py, "File", denied)
    with pytest.raises(DataReadError) as caught:
        DamaskDADF5Adapter.detect(path)
    assert caught.value.__cause__ is failure
    assert "permission denied" in str(caught.value)


def test_damask_detection_distinguishes_a_readable_file_without_markers(tmp_path):
    path = tmp_path / "other.hdf5"
    with h5py.File(path, "w") as handle:
        handle.create_dataset("value", data=[1, 2])
    assert DamaskDADF5Adapter.detect(path) is False
    assert DamaskDADF5Adapter.detect(tmp_path / "other.csv") is False


def test_portable_provenance_keeps_only_documented_fields(tmp_path):
    path = tmp_path / "input.csv"
    path.write_text("value\n1\n", encoding="utf-8")
    provenance = _portable_provenance(
        {
            "source_description": "fixture",
            "input_filename": "/private/input.csv",
            "input_sha256": "a" * 64,
            "operation_log": ["loaded"],
            "arbitrary_extension": "private",
            "token": "secret",
        },
        path,
    )
    assert provenance == {
        "source_description": "fixture",
        "input_filename": "input.csv",
        "input_sha256": "a" * 64,
        "operation_log": ["loaded"],
    }
