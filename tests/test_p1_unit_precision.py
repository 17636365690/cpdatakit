"""Unit mappings must not silently round stored integers or erase tiny values."""

import json

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from cpdatakit.application.contracts import DatasetRequest, ResolvedSchemaMapping
from cpdatakit.application.csv_intake import prepare_csv
from cpdatakit.application.mapping import normalize_value
from cpdatakit.data import ScientificDataset
from cpdatakit.exceptions import DataValidationError, NormalizationError
from cpdatakit.model import Dataset
from cpdatakit.normalization import FieldMapping, normalize_dataset
from cpdatakit.schema import make_field_schema, make_profile_schema
from cpdatakit.schemas import resolve_schema_v2


def _normalize(series, input_unit="N", output_unit="N", shape=()):
    schema = make_profile_schema(
        "measurement",
        [make_field_schema("result", "float", shape=shape, unit=output_unit, allow_missing=True)],
    )
    source = Dataset(pd.DataFrame({"raw": series}), {"units": {"raw": input_unit}})
    return source, normalize_dataset(
        source, schema, [FieldMapping("raw", "result", input_unit, output_unit)]
    )


@pytest.mark.parametrize("output_unit", ["N", "newton", "kg*m/s**2"])
@pytest.mark.parametrize(
    "series",
    [
        pd.Series([2**53 + 1, -(2**63)], dtype="int64"),
        pd.Series([2**64 - 1, 0], dtype="uint64"),
        pd.Series([2**53 + 1, pd.NA], dtype="Int64"),
        pd.Series([2**64 - 1, pd.NA], dtype="UInt64"),
    ],
)
def test_identity_mapping_keeps_exact_integer_storage_and_missing_values(series, output_unit):
    source, result = _normalize(series, output_unit=output_unit)
    pd.testing.assert_series_equal(result.data["result"], series.rename("result"))
    pd.testing.assert_series_equal(source.data["raw"], series.rename("raw"))
    assert result.metadata["units"] == {"result": output_unit}
    assert source.metadata["units"] == {"raw": "N"}


@pytest.mark.parametrize("shape", [(2,), (1, 2), (1, 1, 2)])
def test_identity_mapping_keeps_shaped_integer_values_and_independent_arrays(shape):
    values = np.array([2**53 + 1, 2**64 - 1], dtype="uint64").reshape(shape)
    source, result = _normalize(pd.Series([values]), output_unit="newton", shape=shape)
    np.testing.assert_array_equal(result.data["result"].iloc[0], values, strict=True)
    result.data["result"].iloc[0].flat[0] = 5
    assert int(source.data["raw"].iloc[0].flat[0]) == 2**53 + 1


@pytest.mark.parametrize("value", [2**53 + 1, 2**64 - 1])
def test_real_conversion_rejects_integer_cast_loss_with_field_and_record(value):
    with pytest.raises(NormalizationError, match=r"raw.*record 'sample-b'.*precision"):
        _normalize(pd.Series([value], index=["sample-b"]), "N", "kN")


def test_real_conversion_rejects_rounding_an_exact_integral_result():
    # 4503599627370497 kN = 4503599627370497000 N; float math adds 24 N.
    with pytest.raises(NormalizationError, match=r"raw.*record 0.*precision"):
        _normalize(pd.Series([4503599627370497], dtype="int64"), "kN", "N")


def test_identity_mapping_rejects_mixed_tensor_list_before_numpy_rounds_the_integer():
    with pytest.raises(NormalizationError, match=r"raw.*record 0.*precision"):
        _normalize(pd.Series([[[2**53 + 1, 0.5]]]), shape=(1, 2))


def test_all_missing_series_still_reports_invalid_conversion_as_normalization_error():
    schema = make_profile_schema(
        "measurement", [make_field_schema("result", "float", unit="N", allow_missing=True)]
    )
    with pytest.raises(NormalizationError, match="Cannot convert"):
        normalize_dataset(
            Dataset(pd.DataFrame({"raw": [np.nan]})),
            schema,
            [FieldMapping("raw", "result", "missing_unit", "N")],
        )


@pytest.mark.parametrize(
    ("value", "input_unit", "output_unit"),
    [(1e-300, "ym", "m"), (1e308, "m", "mm"), (-1e-300, "ym", "m")],
)
def test_real_conversion_rejects_overflow_and_underflow_with_location(
    value, input_unit, output_unit
):
    with pytest.raises(NormalizationError, match=r"raw.*record 7.*(overflows|underflows)"):
        _normalize(pd.Series([value], index=[7]), input_unit, output_unit)


def test_identity_mapping_still_rejects_incorrect_shapes():
    with pytest.raises(NormalizationError, match=r"raw.*record 0.*expected shape"):
        _normalize(pd.Series([[1, 2]]), shape=(3,))


def test_real_conversion_preserves_factor_offset_missing_and_preexisting_nonfinite_values():
    _, scaled = _normalize(pd.Series([1000.0, np.nan, np.inf, -np.inf]), "Pa", "kPa")
    np.testing.assert_equal(scaled.data["result"].to_numpy(), [1.0, np.nan, np.inf, -np.inf])
    _, temperatures = _normalize(pd.Series([273.15, 373.15]), "K", "degC")
    np.testing.assert_allclose(temperatures.data["result"], [0.0, 100.0], atol=1e-12)


def test_csv_conversion_failure_reports_original_physical_row_and_column():
    raw = b'note,length\n"two\nlines",1\nlast,1e-300\n'
    columns = [
        {"index": 0, "include": False},
        {
            "index": 1,
            "include": True,
            "target": "length",
            "dtype": "float",
            "input_unit": "ym",
            "output_unit": "m",
            "role": "measurement",
        },
    ]
    with pytest.raises(DataValidationError, match=r"row 4.*column 2.*underflows"):
        prepare_csv(raw, {}, columns)


def _normalize_scientific(tmp_path, values, input_unit, output_unit):
    mapping = tmp_path / "mapping.json"
    mapping.write_text(json.dumps({"mapping_version": "2.0"}), encoding="utf-8")
    schema = resolve_schema_v2(
        {
            "profile": "measurement",
            "schema_version": "2.0",
            "dimensions": [{"name": "sample", "length": len(values)}],
            "variables": [
                {
                    "name": "load",
                    "dims": ["sample"],
                    "dtype": "float",
                    "unit": output_unit,
                    "role": "measurement",
                }
            ],
        }
    )
    source = ScientificDataset(xr.Dataset({"load": ("sample", values, {"unit": input_unit})}))
    request = DatasetRequest(tmp_path / "source.nc", schema, mapping)
    resolved = ResolvedSchemaMapping(
        schema, (FieldMapping("load", "load", input_unit, output_unit),)
    )
    return normalize_value(source, request, resolved)


def test_scientific_identity_mapping_keeps_uint64_without_float_rounding(tmp_path):
    result = _normalize_scientific(tmp_path, np.array([2**64 - 1], dtype="uint64"), "N", "N")
    assert result.data["load"].dtype == np.dtype("uint64")
    assert int(result.data["load"].values[0]) == 2**64 - 1


@pytest.mark.parametrize(
    ("values", "input_unit", "output_unit"),
    [(np.array([1, 2**53 + 1], dtype="int64"), "N", "kN"), (np.array([1.0, 1e-300]), "ym", "m")],
)
def test_scientific_conversion_rejects_precision_loss_with_array_position(
    tmp_path, values, input_unit, output_unit
):
    with pytest.raises(NormalizationError, match=r"load.*(record|index).*(1,|1)"):
        _normalize_scientific(tmp_path, values, input_unit, output_unit)
