from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
import pandas as pd
from hypothesis import given, settings
from hypothesis import strategies as st

from cpdatakit.io import load_dataset, write_hdf5
from cpdatakit.model import Dataset
from cpdatakit.schema import make_field_schema, make_profile_schema
from cpdatakit.validation import validate_dataset


def _codes(result) -> set[str]:
    return {item.code for item in [*result.errors, *result.warnings]}


def _vector_schema():
    return make_profile_schema(
        "point",
        [
            make_field_schema(
                "vector",
                "float",
                required=True,
                shape=[2],
                components=["x", "y"],
                unit="dimensionless",
            )
        ],
    )


@settings(max_examples=50, deadline=None)
@given(
    st.lists(
        st.lists(
            st.floats(allow_nan=False, allow_infinity=False, width=32),
            min_size=0,
            max_size=4,
        ),
        min_size=1,
        max_size=8,
    )
)
def test_malformed_vector_shapes_are_reported_without_crashing(rows) -> None:
    result = validate_dataset(
        Dataset(pd.DataFrame({"vector": rows}), {"units": {"vector": "1"}}),
        _vector_schema(),
    )
    if any(len(row) != 2 for row in rows):
        assert "invalid_shape" in _codes(result)


@settings(max_examples=40, deadline=None)
@given(
    st.lists(
        st.lists(
            st.floats(allow_nan=True, allow_infinity=True, width=32),
            min_size=2,
            max_size=2,
        ),
        min_size=1,
        max_size=6,
    )
)
def test_non_finite_nested_values_are_reported(rows) -> None:
    result = validate_dataset(
        Dataset(pd.DataFrame({"vector": rows}), {"units": {"vector": "1"}}),
        _vector_schema(),
    )
    expected = any(not np.isfinite(value) for row in rows for value in row)
    assert ("non_finite" in _codes(result)) == expected


@settings(max_examples=40, deadline=None)
@given(
    st.lists(
        st.one_of(
            st.integers(-3, 3),
            st.floats(-3, 3, allow_nan=False, allow_infinity=False, width=32),
            st.booleans(),
            st.complex_numbers(allow_nan=False, allow_infinity=False, width=32),
        ),
        min_size=2,
        max_size=2,
    )
)
def test_integer_tensor_dtype_boundaries_do_not_crash(values) -> None:
    schema = make_profile_schema(
        "point",
        [
            make_field_schema(
                "indices",
                "integer",
                required=True,
                shape=[2],
                components=["i", "j"],
                unit="dimensionless",
            )
        ],
    )
    result = validate_dataset(
        Dataset(pd.DataFrame({"indices": [values]}), {"units": {"indices": "1"}}),
        schema,
    )
    assert isinstance(result.valid, bool)


@settings(max_examples=20, deadline=None)
@given(
    vectors=st.lists(
        st.lists(
            st.floats(allow_nan=False, allow_infinity=False, width=32),
            min_size=2,
            max_size=2,
        ),
        min_size=1,
        max_size=4,
    )
)
def test_tensor_hdf5_round_trip_preserves_shape_and_values(vectors) -> None:
    schema = make_profile_schema(
        "point",
        [
            make_field_schema(
                "point_id", "integer", required=True, unit="dimensionless", index=True, unique=True
            ),
            make_field_schema(
                "vector",
                "float",
                required=True,
                shape=[2],
                components=["x", "y"],
                unit="dimensionless",
            ),
        ],
    )
    dataset = Dataset(
        pd.DataFrame({"point_id": range(len(vectors)), "vector": vectors}),
        {"units": {"point_id": "1", "vector": "1"}},
    )
    result = validate_dataset(dataset, schema)
    assert result.valid
    with TemporaryDirectory() as directory:
        output = Path(directory) / "tensor.h5"
        write_hdf5(dataset, output, schema, result, force=True)
        loaded = load_dataset(output)
        assert validate_dataset(loaded, schema).valid
        np.testing.assert_allclose(np.stack(loaded.data["vector"].to_numpy()), np.asarray(vectors))
