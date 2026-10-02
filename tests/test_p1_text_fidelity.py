"""Public text reads must not lose values before schema validation."""

import json

import numpy as np
import pandas as pd
import pytest

from cpdatakit.exceptions import DataReadError
from cpdatakit.io import load_dataset


@pytest.mark.parametrize("suffix", ["csv", "json"])
@pytest.mark.parametrize("value", [9007199254740993, 9223372036854775807, 18446744073709551615])
def test_integer_with_missing_is_exact_before_validation(tmp_path, suffix, value):
    source = tmp_path / f"input.{suffix}"
    original = (
        f"id,note\n{value},first\n,second\n"
        if suffix == "csv"
        else json.dumps([{"id": value, "note": "first"}, {"id": None, "note": "second"}])
    ).encode()
    source.write_bytes(original)
    frame = load_dataset(source).data
    assert int(frame["id"].iloc[0]) == value
    assert pd.isna(frame["id"].iloc[1])
    assert pd.api.types.is_integer_dtype(frame["id"].dtype)
    assert source.read_bytes() == original


@pytest.mark.parametrize(
    "suffix,content",
    [
        ("csv", "x\n9007199254740993\n0.5\n"),
        ("json", '[{"x":9007199254740993},{"x":0.5}]'),
        ("json", '[{"x":[9007199254740993,0.5]}]'),
        ("csv", "x\n1e-999\n"),
        ("json", '[{"x":1e-999}]'),
        ("json", '[{"x":[1e-999,1.0]}]'),
        ("csv", "x\n1e999\n"),
        ("json", '[{"x":1e999}]'),
    ],
)
def test_numeric_promotion_or_parse_loss_is_rejected(tmp_path, suffix, content):
    source = tmp_path / f"input.{suffix}"
    source.write_text(content, encoding="utf-8")
    with pytest.raises(DataReadError, match=r"precision|loss|underflow|overflow"):
        load_dataset(source)
    assert source.read_text(encoding="utf-8") == content


def test_float_csv_uses_roundtrip_precision(tmp_path):
    source = tmp_path / "input.csv"
    source.write_text("x\n0.12345678901234568\n", encoding="utf-8")
    assert load_dataset(source).data["x"].iloc[0] == float("0.12345678901234568")


@pytest.mark.parametrize("suffix", ["csv", "json"])
def test_safe_mixed_numeric_values_remain_readable(tmp_path, suffix):
    source = tmp_path / f"input.{suffix}"
    source.write_text(
        "x,label\n1,甲\n0.5,乙\n"
        if suffix == "csv"
        else '[{"x":1,"label":"甲"},{"x":0.5,"label":"乙"}]',
        encoding="utf-8",
    )
    frame = load_dataset(source).data
    assert frame["x"].tolist() == [1.0, 0.5]
    assert frame["label"].tolist() == ["甲", "乙"]


def test_ordinary_csv_missing_and_header_inference_remains_compatible(tmp_path):
    source = tmp_path / "input.csv"
    source.write_text('id,label,label\n001,NA,"quoted, text"\n002,ok,tail\n', encoding="utf-8")
    frame = load_dataset(source).data
    assert list(frame) == ["id", "label", "label.1"]
    assert frame["id"].tolist() == [1, 2]
    assert pd.isna(frame["label"].iloc[0])
    assert frame["label.1"].iloc[0] == "quoted, text"


def test_json_integer_arrays_preserve_values(tmp_path):
    source = tmp_path / "input.json"
    source.write_text('[{"x":[9007199254740993,9007199254740995]}]', encoding="utf-8")
    values = np.asarray(load_dataset(source).data["x"].iloc[0])
    assert values.dtype.kind in "iu"
    assert [int(item) for item in values] == [9007199254740993, 9007199254740995]


def test_json_empty_records_keep_their_record_count(tmp_path):
    source = tmp_path / "input.json"
    source.write_text("[{},{}]", encoding="utf-8")
    assert len(load_dataset(source).data) == 2


def test_csv_inferred_index_does_not_misalign_column_values(tmp_path):
    source = tmp_path / "input.csv"
    source.write_text("a,b\nx,1,2\ny,3,4\n", encoding="utf-8")
    frame = load_dataset(source).data
    assert frame.index.tolist() == ["x", "y"]
    assert frame["a"].tolist() == [1, 3]
    assert frame["b"].tolist() == [2, 4]


@pytest.mark.parametrize("suffix", ["csv", "json"])
@pytest.mark.parametrize(
    "token", ["1e9999999999999999999", "1" * 4301], ids=["extreme-exponent", "oversized-integer"]
)
def test_extreme_numeric_tokens_are_actionable_read_errors(tmp_path, suffix, token):
    source = tmp_path / f"input.{suffix}"
    content = f"x\n{token}\n" if suffix == "csv" else '[{"x":' + token + "}]"
    source.write_text(content, encoding="utf-8")
    with pytest.raises(DataReadError, match=r"[Ff]ield 'x'.*record 1"):
        load_dataset(source)
