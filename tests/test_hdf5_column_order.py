"""HDF5 table reads preserve stored order without inferring it from a schema."""

from pathlib import Path

import h5py
import numpy as np
import pandas as pd
import pytest

from cpdatakit.io import iter_hdf5_chunks, load_hdf5, write_hdf5
from cpdatakit.model import Dataset
from cpdatakit.schema import (
    make_field_schema,
    make_profile_schema,
    schema_sha256,
    schema_to_canonical_json,
)
from cpdatakit.validation import validate_dataset


def _schema():
    # Schema declaration order deliberately differs from the data's column order.
    return make_profile_schema(
        "column-order",
        [
            make_field_schema("m", "integer", required=True, shape=[2], unit="1"),
            make_field_schema("z", "integer", required=True, unit="1"),
            make_field_schema("a", "float", required=True, unit="1"),
        ],
    )


@pytest.fixture
def ordered_hdf5(tmp_path: Path) -> Path:
    dataset = Dataset(
        pd.DataFrame(
            {
                "z": np.array([2**53 + 1, 2**53 + 3, 2**53 + 5], dtype=np.int64),
                "user_tag": ["first", "second", "third"],
                "a": np.array([0.25, 0.5, 0.75], dtype=np.float32),
                "m": [
                    np.array([1, 2], dtype=np.int16),
                    np.array([3, 4], dtype=np.int16),
                    np.array([5, 6], dtype=np.int16),
                ],
            }
        )
    )
    schema = _schema()
    validation = validate_dataset(dataset, schema)
    assert validation.valid, validation.to_dict()
    output = tmp_path / "ordered.h5"
    write_hdf5(dataset, output, schema, validation, hdf5_chunk_size=2)
    return output


def test_hdf5_default_read_keeps_input_order_including_extension_columns(ordered_hdf5: Path):
    loaded = load_hdf5(ordered_hdf5)

    assert list(loaded.data.columns) == ["z", "user_tag", "a", "m"]
    assert loaded.data.shape == (3, 4)
    assert loaded.data["z"].tolist() == [2**53 + 1, 2**53 + 3, 2**53 + 5]
    assert loaded.data["z"].dtype == np.dtype("int64")
    assert loaded.data["a"].tolist() == [0.25, 0.5, 0.75]
    assert loaded.data["a"].dtype == np.dtype("float32")
    assert loaded.data["user_tag"].tolist() == ["first", "second", "third"]
    values = np.stack(loaded.data["m"])
    np.testing.assert_array_equal(values, [[1, 2], [3, 4], [5, 6]])
    assert values.dtype == np.dtype("int16")
    assert values.shape == (3, 2)


def test_hdf5_default_chunks_keep_input_order(ordered_hdf5: Path):
    chunks = list(iter_hdf5_chunks(ordered_hdf5, chunk_size=2))

    assert [list(chunk.data.columns) for chunk in chunks] == [
        ["z", "user_tag", "a", "m"],
        ["z", "user_tag", "a", "m"],
    ]
    assert [chunk.data["z"].tolist() for chunk in chunks] == [
        [2**53 + 1, 2**53 + 3],
        [2**53 + 5],
    ]
    assert [chunk.data["user_tag"].tolist() for chunk in chunks] == [
        ["first", "second"],
        ["third"],
    ]


def test_hdf5_selected_read_uses_requested_order_and_range(ordered_hdf5: Path):
    loaded = load_hdf5(ordered_hdf5, fields=["m", "user_tag", "z"], start=1, stop=3)

    assert list(loaded.data.columns) == ["m", "user_tag", "z"]
    assert loaded.data["user_tag"].tolist() == ["second", "third"]
    assert loaded.data["z"].tolist() == [2**53 + 3, 2**53 + 5]
    np.testing.assert_array_equal(np.stack(loaded.data["m"]), [[3, 4], [5, 6]])


def test_hdf5_selected_chunks_use_requested_order(ordered_hdf5: Path):
    chunks = list(iter_hdf5_chunks(ordered_hdf5, fields=["m", "z"], chunk_size=2))

    assert [list(chunk.data.columns) for chunk in chunks] == [["m", "z"], ["m", "z"]]
    assert [chunk.data["z"].tolist() for chunk in chunks] == [
        [2**53 + 1, 2**53 + 3],
        [2**53 + 5],
    ]
    np.testing.assert_array_equal(np.stack(chunks[1].data["m"]), [[5, 6]])


@pytest.mark.parametrize("with_schema_snapshot", [False, True])
def test_legacy_hdf5_keeps_existing_order_without_guessing_from_schema(
    tmp_path: Path, with_schema_snapshot: bool
):
    path = tmp_path / "legacy.h5"
    with h5py.File(path, "w") as handle:
        handle.attrs.update(
            {
                "format": "CPDataKit",
                "format_version": "1.0",
                "profile": "column-order" if with_schema_snapshot else "curve",
                "schema_version": "1.0",
                "units_json": "{}",
                "field_mapping_json": "{}",
                "provenance_json": "{}",
                "validation_summary_json": '{"valid": true}',
            }
        )
        if with_schema_snapshot:
            handle.attrs["schema_json"] = schema_to_canonical_json(_schema())
            handle.attrs["schema_sha256"] = schema_sha256(_schema())
        group = handle.create_group("data", track_order=False)
        group.create_dataset("z", data=np.array([7, 8], dtype=np.int64))
        group.create_dataset("user_code", data=np.array([10, 20], dtype=np.int16))
        group.create_dataset("a", data=np.array([0.5, 0.75], dtype=np.float32))
        group.create_dataset("m", data=np.array([[1, 2], [3, 4]], dtype=np.int16))

    loaded = load_hdf5(path)

    assert list(loaded.data.columns) == ["a", "m", "user_code", "z"]
    assert loaded.data["z"].tolist() == [7, 8]
    assert loaded.data["a"].tolist() == [0.5, 0.75]
    assert loaded.data["user_code"].tolist() == [10, 20]
    np.testing.assert_array_equal(np.stack(loaded.data["m"]), [[1, 2], [3, 4]])
