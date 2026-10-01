"""CSV intake contracts: explicit declarations, traceability and loss prevention."""

import hashlib
import importlib
import importlib.util
import json

import pytest

from cpdatakit.exceptions import DataValidationError
from cpdatakit.io import load_dataset, write_hdf5
from cpdatakit.validation import validate_dataset


@pytest.fixture
def intake():
    class IntakeModule:
        def __getattr__(self, attribute):
            name = "cpdatakit.application.csv_intake"
            assert importlib.util.find_spec(name) is not None, "CSV intake is not implemented"
            return getattr(importlib.import_module(name), attribute)

    return IntakeModule()


def column(index=0, target="value", **overrides):
    return {
        "index": index,
        "include": True,
        "target": target,
        "dtype": "float",
        "input_unit": "MPa",
        "output_unit": "MPa",
        "role": "measured",
        **overrides,
    }


def test_preview_semicolon_bom_blank_lines_and_unit_row(intake):
    raw = "\ufeffInstrument export\nTime;Force;Note\n(sec);(kN);\n\n0;1.25;start\n1;2.5;end\n"
    result = intake.preview_csv(raw.encode(), {"delimiter": ";", "header_row": 2, "unit_row": 3})
    assert result["record_count"] == 2
    assert result["source_sha256"] == hashlib.sha256(raw.encode()).hexdigest()
    assert [item["source_name"] for item in result["columns"]] == ["Time", "Force", "Note"]
    assert result["columns"][0]["suggested_unit"] == "sec"
    assert result["columns"][1]["dtype"] == "float"
    assert result["columns"][1]["samples"] == ["1.25", "2.5"]


def test_preview_preserves_duplicate_and_blank_header_by_index(intake):
    result = intake.preview_csv(b"x,,x\n1,2,3\n")
    assert [(item["index"], item["source_name"]) for item in result["columns"]] == [
        (0, "x"),
        (1, ""),
        (2, "x"),
    ]


def test_header_units_are_only_suggestions(intake):
    result = intake.preview_csv(b"Time (sec),Strain (%)\n0,1\n")
    assert [item["suggested_unit"] for item in result["columns"]] == ["sec", "%"]
    with pytest.raises(DataValidationError, match="unit"):
        intake.prepare_csv(b"Time (sec)\n1\n", {}, [column(input_unit="", output_unit="")])


def test_wrong_default_separator_warns_without_silent_sniffing(intake):
    result = intake.preview_csv(b"x;y\n1;2\n")
    assert len(result["columns"]) == 1
    assert any("delimiter" in warning.lower() for warning in result["warnings"])


def test_preview_samples_are_bounded(intake):
    result = intake.preview_csv(b"x\n0\n1\n2\n3\n4\n5\n")
    assert result["record_count"] == 6
    assert result["columns"][0]["samples"] == ["0", "1", "2", "3", "4"]


def test_no_header_and_gb18030_decimal_comma(intake):
    options = {"header_row": 0, "delimiter": ";", "decimal": ",", "encoding": "gb18030"}
    raw = "1,25;试样甲\n2,50;试样乙\n".encode("gb18030")
    preview = intake.preview_csv(raw, options)
    assert preview["record_count"] == 2
    result = intake.prepare_csv(
        raw,
        options,
        [column(), column(1, "specimen", dtype="string", input_unit=None, output_unit=None)],
    )
    assert result.value.data["value"].tolist() == [1.25, 2.5]
    assert result.value.data["specimen"].tolist() == ["试样甲", "试样乙"]


def test_prepare_converts_declared_units_and_records_exclusions(intake):
    raw = b"time;force;note\n(sec);(kN);\n0;1.25;start\n1;2.5;end\n"
    options = {"delimiter": ";", "unit_row": 2}
    declarations = [
        column(0, "time", input_unit="s", output_unit="s", role="time"),
        column(1, "force", input_unit="kN", output_unit="N"),
        {"index": 2, "include": False},
    ]
    result = intake.prepare_csv(raw, options, declarations, source_name="force.csv")
    assert result.value.data.columns.tolist() == ["time", "force"]
    assert result.value.data["force"].tolist() == [1250.0, 2500.0]
    assert validate_dataset(result.value, result.schema).valid
    assert result.value.metadata["units"] == {"time": "s", "force": "N"}
    assert result.manifest["source_name"] == "force.csv"
    assert result.manifest["source_sha256"] == hashlib.sha256(raw).hexdigest()
    assert result.manifest["excluded_columns"] == [{"index": 2, "source_name": "note"}]
    assert result.manifest["columns"][1]["input_unit"] == "kN"
    assert result.manifest["columns"][1]["output_unit"] == "N"
    assert result.value.metadata["provenance"]["csv_import"] == result.manifest
    json.dumps(result.manifest, allow_nan=False)


def test_explicit_source_order_survives_reordered_declarations(intake):
    result = intake.prepare_csv(b"z,a\n1,2\n", {}, [column(1, "a"), column(0, "z")])
    assert result.value.data.columns.tolist() == ["z", "a"]
    assert [field.name for field in result.schema.fields] == ["z", "a"]


def test_duplicate_blank_names_can_be_mapped_to_unique_targets(intake):
    result = intake.prepare_csv(
        b"x,,x\n1,2,3\n", {}, [column(0, "first"), column(1, "middle"), column(2, "last")]
    )
    assert result.value.data.iloc[0].tolist() == [1, 2, 3]


def test_confirmed_source_hash_rejects_replaced_payload(intake):
    with pytest.raises(DataValidationError, match="sha256"):
        intake.prepare_csv(b"x\n2\n", {}, [column()], source_sha256="0" * 64)


@pytest.mark.parametrize(
    "declarations",
    [
        [],
        [column(1)],
        [column(), column()],
        [column(), column(1)],
        [{"index": 0, "include": False}],
        [column(target=" ")],
        [column(include="false")],
        [column(index=True)],
        [column(dtype="number")],
    ],
)
def test_invalid_column_selection_is_rejected(intake, declarations):
    with pytest.raises(DataValidationError):
        intake.prepare_csv(b"x\n1\n", {}, declarations)


def test_duplicate_targets_rejected(intake):
    with pytest.raises(DataValidationError, match="target"):
        intake.prepare_csv(b"a,b\n1,2\n", {}, [column(), column(1)])


@pytest.mark.parametrize("field", ["input_unit", "output_unit", "role"])
def test_numeric_declarations_require_explicit_units_and_role(intake, field):
    with pytest.raises(DataValidationError, match=field.split("_")[-1]):
        intake.prepare_csv(b"x\n1\n", {}, [column(**{field: ""})])


@pytest.mark.parametrize("token", ["", "NA", "bad", "NaN", "inf", "-inf", "1e999"])
def test_numeric_errors_locate_original_line_and_column(intake, token):
    raw = f"name,x\nsample,{token}\n".encode()
    with pytest.raises(DataValidationError, match=r"row 2.*column 2"):
        intake.prepare_csv(raw, {}, [{"index": 0, "include": False}, column(1)])


@pytest.mark.parametrize("payload", [b"a,b\n1\n", b"a,b\n1,2,3\n"])
def test_ragged_rows_rejected_with_original_line(intake, payload):
    with pytest.raises(DataValidationError, match="row 2"):
        intake.preview_csv(payload)


def test_integer_values_above_float_precision_are_preserved(intake):
    result = intake.prepare_csv(
        b"id\n9007199254740993\n9007199254740995\n",
        {},
        [column(dtype="integer", input_unit="dimensionless", output_unit="dimensionless")],
    )
    assert result.value.data["value"].tolist() == [9007199254740993, 9007199254740995]
    assert result.value.data["value"].dtype.kind in "iu"


def test_large_integer_conversion_does_not_silently_round(intake):
    with pytest.raises(DataValidationError, match=r"row 2.*column 1"):
        intake.prepare_csv(
            b"id\n9007199254740993\n",
            {},
            [column(dtype="integer", input_unit="mm", output_unit="m")],
        )


@pytest.mark.parametrize("token", ["1.5", "18446744073709551616"])
def test_invalid_integer_is_rejected_without_truncation(intake, token):
    with pytest.raises(DataValidationError, match=r"row 2.*column 1"):
        intake.prepare_csv(f"id\n{token}\n".encode(), {}, [column(dtype="integer")])


def test_boolean_values_and_quoted_newlines(intake):
    result = intake.prepare_csv(
        b'flag,note\ntrue,"line1\nline2"\nfalse,ok\n',
        {},
        [
            column(0, "flag", dtype="boolean", input_unit=None, output_unit=None),
            column(1, "note", dtype="string", input_unit=None, output_unit=None),
        ],
    )
    assert result.value.data["flag"].tolist() == [True, False]
    assert result.value.data["note"].tolist() == ["line1\nline2", "ok"]


@pytest.mark.parametrize(
    "options",
    [
        {"delimiter": "|"},
        {"decimal": ":"},
        {"encoding": "latin1"},
        {"header_row": -1},
        {"header_row": True},
        {"header_row": 1, "unit_row": 1},
        {"header_row": 8},
        {"unit_row": 8},
        {"unrecognised": 1},
    ],
)
def test_invalid_options_do_not_fall_back_silently(intake, options):
    with pytest.raises(DataValidationError):
        intake.preview_csv(b"x\n1\n", options)


def test_payload_and_row_limits_are_enforced(intake):
    with pytest.raises(DataValidationError, match="byte"):
        intake.preview_csv(b"x\n1\n", max_bytes=3)
    with pytest.raises(DataValidationError, match="row"):
        intake.preview_csv(b"x\n1\n2\n", max_rows=1)


@pytest.mark.parametrize("payload", [b"", b"x\n", b"\xff\n", b'x\n"unclosed\n'])
def test_empty_undecodable_and_malformed_inputs_are_rejected(intake, payload):
    with pytest.raises(DataValidationError):
        intake.preview_csv(payload)


def test_incompatible_units_fail_before_returning_prepared_data(intake):
    with pytest.raises(DataValidationError, match="unit"):
        intake.prepare_csv(b"x\n1\n", {}, [column(input_unit="s", output_unit="MPa")])


def test_invalid_identical_units_are_not_blessed_as_declared(intake):
    with pytest.raises(DataValidationError, match="unit"):
        intake.prepare_csv(b"x\n1\n", {}, [column(input_unit="nonesuch", output_unit="nonesuch")])


def test_integer_unit_conversion_must_not_round_a_fraction_to_an_integer(intake):
    # 9007199254739999 mm = 9007199254739.999 m, even if float math rounds it.
    with pytest.raises(DataValidationError, match=r"row 2.*column 1"):
        intake.prepare_csv(
            b"x\n9007199254739999\n",
            {},
            [column(dtype="integer", input_unit="mm", output_unit="m")],
        )


def test_exact_integer_unit_conversion_retains_integer_storage(intake):
    result = intake.prepare_csv(
        b"x\n1000\n2000\n", {}, [column(dtype="integer", input_unit="mm", output_unit="m")]
    )
    assert result.value.data["value"].tolist() == [1, 2]
    assert result.value.data["value"].dtype.kind == "i"


def test_float_input_underflow_is_not_silently_zero(intake):
    with pytest.raises(DataValidationError, match=r"row 2.*column 1"):
        intake.prepare_csv(b"x\n1e-999\n", {}, [column()])


@pytest.mark.parametrize("token", ["1e308", "1e-323"])
def test_unit_conversion_overflow_or_underflow_locates_the_value(intake, token):
    input_unit, output_unit = ("m", "mm") if token == "1e308" else ("mm", "m")
    with pytest.raises(DataValidationError, match=r"row 2.*column 1"):
        intake.prepare_csv(
            f"x\n{token}\n".encode(), {}, [column(input_unit=input_unit, output_unit=output_unit)]
        )


@pytest.mark.parametrize("dtype,token", [("boolean", "yes"), ("string", " ")])
def test_invalid_non_numeric_values_have_locations(intake, dtype, token):
    with pytest.raises(DataValidationError, match=r"row 2.*column 2"):
        intake.prepare_csv(
            f"a,b\n1,{token}\n".encode(),
            {},
            [
                {"index": 0, "include": False},
                column(1, dtype=dtype, input_unit=None, output_unit=None),
            ],
        )


@pytest.mark.parametrize("target", ["a/b", "/outside", "a/", "\x00", "a\x00b", ".", ".."])
def test_unsafe_hdf5_field_names_are_rejected_before_preparing_data(intake, target):
    with pytest.raises(DataValidationError, match=r"Column 1.*target"):
        intake.prepare_csv(b"x\n1\n", {}, [column(target=target)])


def test_unicode_field_name_roundtrips_prepared_csv_through_hdf5(intake, tmp_path):
    prepared = intake.prepare_csv(b"x\n1\n", {}, [column(target="载荷 \u03c3")])
    output = tmp_path / "confirmed.h5"
    write_hdf5(
        prepared.value,
        output,
        schema=prepared.schema,
        validation=validate_dataset(prepared.value, prepared.schema),
    )
    restored = load_dataset(output)
    assert restored.data.columns.tolist() == ["载荷 \u03c3"]
    assert restored.data["载荷 \u03c3"].tolist() == [1.0]
    assert validate_dataset(restored, prepared.schema).valid


@pytest.mark.parametrize("blank", ['""', '" "', " "])
def test_single_column_empty_values_are_not_dropped_as_blank_lines(intake, blank):
    payload = f"x\n1\n{blank}\n2\n".encode()
    assert intake.preview_csv(payload)["record_count"] == 3
    with pytest.raises(DataValidationError, match=r"row 3.*column 1.*missing"):
        intake.prepare_csv(payload, {}, [column()])


def test_empty_quoted_header_has_column_identity(intake):
    preview = intake.preview_csv(b'""\n1\n2\n')
    assert preview["record_count"] == 2
    assert preview["columns"][0]["source_name"] == ""
    assert preview["columns"][0]["index"] == 0


@pytest.mark.parametrize("token", ["9007199254740993e0", "9007199254740993.0", "9007199254740993"])
def test_large_integral_float_inputs_are_not_silently_rounded(intake, token):
    with pytest.raises(DataValidationError, match=r"row 2.*column 1.*integer"):
        intake.prepare_csv(f"x\n{token}\n".encode(), {}, [column(dtype="float")])


def test_ordinary_fractional_float_input_remains_supported(intake):
    result = intake.prepare_csv(b"x\n0.1\n0.2\n", {}, [column()])
    assert result.value.data["value"].tolist() == [0.1, 0.2]


def test_explicit_integer_accepts_exact_large_exponent_values(intake):
    result = intake.prepare_csv(b"id\n9007199254740993e0\n", {}, [column(dtype="integer")])
    assert result.value.data["value"].tolist() == [9007199254740993]


def test_row_limit_stops_before_reading_malformed_tail(intake):
    with pytest.raises(DataValidationError, match="row limit"):
        intake.preview_csv(b'x\n1\n2\n"unclosed\n', max_rows=1)


def test_row_limit_ignores_metadata_rows_and_physical_blank_lines(intake):
    preview = intake.preview_csv(
        b"Instrument\nx\nMPa\n\n1\n\n2\n", {"header_row": 2, "unit_row": 3}, max_rows=2
    )
    assert preview["record_count"] == 2
