"""Bounded CSV intake with explicit field declarations and auditable normalization.

Column indexes are zero based. Header/unit row numbers refer to one-based physical
line starts, including blank lines; zero disables the respective special row.
Unit suggestions never become declarations without the caller confirming them.
"""

from __future__ import annotations

import csv
import hashlib
import io
import math
import re
from copy import deepcopy
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, localcontext
from typing import Any

import numpy as np
import pandas as pd
from pint import UnitRegistry
from pint.errors import PintError

from ..exceptions import CPDataKitError, DataValidationError
from ..model import Dataset
from ..normalization import FieldMapping, normalize_dataset
from ..schema import FieldSchema, ProfileSchema, load_schema
from ..validation import validate_dataset

_UREG = UnitRegistry(non_int_type=Decimal)
_DEFAULT_OPTIONS = {
    "delimiter": ",",
    "header_row": 1,
    "unit_row": 0,
    "decimal": ".",
    "encoding": "utf-8-sig",
}
_NUMBER = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?\Z")


@dataclass(slots=True)
class CsvPrepared:
    """Validated normalized data, its confirmed contract and the import receipt."""

    value: Dataset
    schema: ProfileSchema
    manifest: dict[str, Any]


@dataclass(slots=True)
class _Parsed:
    options: dict[str, Any]
    names: list[str]
    units: list[str | None]
    rows: list[tuple[int, list[str]]]
    sha256: str
    warnings: list[str]


def _options(options: dict | None) -> dict[str, Any]:
    if options is not None and not isinstance(options, dict):
        raise DataValidationError("CSV options must be an object")
    supplied = options or {}
    if set(supplied) - set(_DEFAULT_OPTIONS):
        raise DataValidationError("Unsupported CSV option; check delimiter/row/decimal/encoding")
    result = {**_DEFAULT_OPTIONS, **supplied}
    for key, allowed in (
        ("delimiter", (",", ";", "\t")),
        ("decimal", (".", ",")),
        ("encoding", ("utf-8-sig", "gb18030")),
    ):
        if result[key] not in allowed:
            raise DataValidationError(f"Unsupported CSV {key}: {result[key]!r}")
    for key in ("header_row", "unit_row"):
        if type(result[key]) is not int or result[key] < 0:
            raise DataValidationError(f"CSV {key} must be a nonnegative row number")
    if result["header_row"] and result["header_row"] == result["unit_row"]:
        raise DataValidationError("CSV header_row and unit_row must be different")
    if result["unit_row"] and result["unit_row"] < result["header_row"]:
        raise DataValidationError("CSV unit_row must follow header_row")
    return result


def _suggested_unit(text: str, *, standalone: bool = False) -> str | None:
    value = text.strip()
    enclosed = re.search(r"(?:\(([^()]*)\)|\[([^\[\]]*)\])\s*$", value)
    if enclosed:
        return (enclosed.group(1) or enclosed.group(2) or "").strip() or None
    return value or None if standalone else None


def _parse(payload: bytes, options: dict | None, max_bytes: int, max_rows: int) -> _Parsed:
    opts = _options(options)
    for label, limit in (("byte", max_bytes), ("row", max_rows)):
        if type(limit) is not int or limit <= 0:
            raise DataValidationError(f"CSV {label} limit must be a positive integer")
    if not isinstance(payload, bytes):
        raise DataValidationError("CSV payload must be bytes")
    if len(payload) > max_bytes:
        raise DataValidationError(f"CSV byte limit exceeded: {len(payload)} > {max_bytes}")
    try:
        text = payload.decode(opts["encoding"])
    except UnicodeError as exc:
        raise DataValidationError(f"CSV encoding {opts['encoding']!r} cannot decode input") from exc
    if "\x00" in text:
        raise DataValidationError("CSV input contains NUL bytes; select a supported text encoding")
    reader = csv.reader(io.StringIO(text, newline=""), delimiter=opts["delimiter"], strict=True)
    header, unit = opts["header_row"], opts["unit_row"]
    names: list[str] | None = None
    unit_values: list[str] | None = None
    rows: list[tuple[int, list[str]]] = []
    try:
        while True:
            line = reader.line_num + 1
            try:
                cells = next(reader)
            except StopIteration:
                break
            # csv.reader distinguishes an empty physical line ([]) from a
            # record with one empty field ([""]). Only the former is skipped.
            if not cells:
                continue
            if line == header:
                names = cells
            if line <= header:
                continue
            if line == unit:
                unit_values = cells
                continue
            if names is None:
                if header:
                    raise DataValidationError(f"CSV header_row row {header} has no record")
                names = [f"column_{i + 1}" for i in range(len(cells))]
            if len(rows) >= max_rows:
                raise DataValidationError(f"CSV row limit exceeded: more than {max_rows} rows")
            if len(cells) != len(names):
                raise DataValidationError(
                    f"CSV row {line} has {len(cells)} columns; expected {len(names)}. "
                    "Check delimiter and quoted values."
                )
            rows.append((line, cells))
    except csv.Error as exc:
        raise DataValidationError(f"Malformed CSV at row {reader.line_num}: {exc}") from exc
    for label, number, entry in (("header_row", header, names), ("unit_row", unit, unit_values)):
        if number and entry is None:
            raise DataValidationError(f"CSV {label} row {number} does not contain a record")
    if not rows or names is None:
        raise DataValidationError("CSV contains no data rows")
    width = len(names)
    if unit_values is not None and len(unit_values) != width:
        raise DataValidationError(
            f"CSV row {unit} has {len(unit_values)} columns; expected {width}. "
            "Check delimiter and quoted values."
        )
    units = [
        _suggested_unit(unit_values[i], standalone=True)
        if unit_values is not None
        else _suggested_unit(name)
        for i, name in enumerate(names)
    ]
    warnings = []
    if width == 1 and any(
        separator in names[0] or separator in rows[0][1][0]
        for separator in (",", ";", "\t")
        if separator != opts["delimiter"]
    ):
        warnings.append("Only one column was read; check the delimiter before confirming fields.")
    if any(units):
        warnings.append("Units from headers are suggestions and require explicit confirmation.")
    return _Parsed(opts, names, units, rows, hashlib.sha256(payload).hexdigest(), warnings)


def _number_token(text: str, decimal: str) -> str:
    token = text.strip()
    if decimal == ",":
        if "." in token:
            raise ValueError("decimal point conflicts with selected comma decimal separator")
        token = token.replace(",", ".")
    if not _NUMBER.fullmatch(token):
        raise ValueError("expected a finite number without thousands separators")
    return token


def _dtype(values: list[str], decimal: str) -> str:
    stripped = [value.strip() for value in values]
    if all(value.lower() in ("true", "false") for value in stripped):
        return "boolean"
    try:
        tokens = [_number_token(value, decimal) for value in values]
    except ValueError:
        return "string"
    return "integer" if all(re.fullmatch(r"[+-]?[0-9]+", value) for value in tokens) else "float"


def preview_csv(
    payload: bytes,
    options: dict | None = None,
    *,
    max_bytes: int = 64 * 1024 * 1024,
    max_rows: int = 100000,
) -> dict:
    """Preview every column without accepting any scientific or unit declaration."""
    parsed = _parse(payload, options, max_bytes, max_rows)
    return {
        "source_sha256": parsed.sha256,
        "record_count": len(parsed.rows),
        "options": dict(parsed.options),
        "columns": [
            {
                "index": i,
                "source_name": name,
                "dtype": _dtype([cells[i] for _, cells in parsed.rows], parsed.options["decimal"]),
                "suggested_unit": parsed.units[i],
                "samples": [cells[i] for _, cells in parsed.rows[:5]],
            }
            for i, name in enumerate(parsed.names)
        ],
        "warnings": parsed.warnings,
    }


def _declarations(columns: list[dict], names: list[str]) -> list[dict]:
    if not isinstance(columns, list) or len(columns) != len(names):
        raise DataValidationError("Every original column must have exactly one declaration")
    by_index = {}
    targets = set()
    for raw in columns:
        if not isinstance(raw, dict) or type(raw.get("index")) is not int:
            raise DataValidationError("Each column index must be an integer")
        index = raw["index"]
        if not 0 <= index < len(names) or index in by_index:
            raise DataValidationError(f"Duplicate or unknown column index: {index}")
        if type(raw.get("include")) is not bool:
            raise DataValidationError(f"Column {index + 1} include must be boolean")
        item = {"index": index, "source_name": names[index], "include": raw["include"]}
        by_index[index] = item
        if not raw["include"]:
            continue
        for key in ("target", "dtype", "role"):
            if not isinstance(raw.get(key), str) or not raw[key].strip():
                raise DataValidationError(f"Column {index + 1} requires explicit {key}")
            item[key] = raw[key].strip()
        target = item["target"]
        if "/" in target or "\x00" in target or target in (".", ".."):
            raise DataValidationError(
                f"Column {index + 1} target must be a flat field name: "
                "'/', NUL, '.' and '..' are not supported"
            )
        if item["target"] in targets:
            raise DataValidationError(f"Duplicate target field: {item['target']!r}")
        targets.add(item["target"])
        if item["dtype"] not in ("float", "integer", "string", "boolean"):
            raise DataValidationError(f"Column {index + 1} has unsupported dtype")
        for key in ("input_unit", "output_unit"):
            value = raw.get(key)
            if value is not None and not isinstance(value, str):
                raise DataValidationError(f"Column {index + 1} {key} must be text")
            item[key] = value.strip() or None if isinstance(value, str) else None
        if item["dtype"] in ("float", "integer"):
            if not item["input_unit"] or not item["output_unit"]:
                raise DataValidationError(f"Column {index + 1} requires explicit input/output unit")
            try:
                _UREG.Quantity(Decimal(1), item["input_unit"]).to(item["output_unit"])
            except (PintError, ValueError, TypeError) as exc:
                raise DataValidationError(
                    f"Column {index + 1} has invalid/incompatible units"
                ) from exc
        elif item["input_unit"] or item["output_unit"]:
            raise DataValidationError(f"Column {index + 1}: units apply only to numeric fields")
    if not targets:
        raise DataValidationError("At least one column must be included")
    return [by_index[index] for index in range(len(names))]


def _cell_error(line: int, item: dict, text: str, reason: str) -> DataValidationError:
    return DataValidationError(
        f"CSV row {line}, column {item['index'] + 1} ({item['source_name']!r}): "
        f"{reason}; value={text[:80]!r}"
    )


def _series(parsed: _Parsed, item: dict) -> pd.Series:
    values = []
    dtype = item["dtype"]
    for line, cells in parsed.rows:
        text = cells[item["index"]]
        try:
            if not text.strip():
                raise ValueError("missing value")
            if dtype == "string":
                value = text
            elif dtype == "boolean":
                if text.strip().lower() not in ("true", "false", "1", "0"):
                    raise ValueError("expected boolean true/false or 1/0")
                value = text.strip().lower() in ("true", "1")
            elif dtype == "integer":
                exact = Decimal(_number_token(text, parsed.options["decimal"]))
                if exact != exact.to_integral_value() or not -(2**63) <= exact < 2**64:
                    raise ValueError("expected an exact 64-bit integer")
                value = int(exact)
                if item["input_unit"] != item["output_unit"] and abs(value) > 2**53:
                    raise ValueError("integer unit conversion cannot guarantee exact precision")
            else:
                token = _number_token(text, parsed.options["decimal"])
                exact = Decimal(token)
                value = float(token)
                if not math.isfinite(value):
                    raise ValueError("expected a finite number")
                if value == 0 and exact != 0:
                    raise ValueError("number underflows float64; refusing to replace it with zero")
                if exact == exact.to_integral_value() and Decimal.from_float(value) != exact:
                    raise ValueError(
                        "integer cannot be represented exactly as float64; select integer dtype"
                    )
            values.append(value)
        except (ValueError, InvalidOperation, OverflowError) as exc:
            raise _cell_error(line, item, text, str(exc)) from exc
    if dtype == "integer":
        if min(values) < 0 and max(values) >= 2**63:
            raise _cell_error(parsed.rows[0][0], item, "", "mixed integer range exceeds int64")
        storage = "uint64" if max(values) >= 2**63 else "int64"
    else:
        storage = {"float": "float64", "string": "object", "boolean": "bool"}[dtype]
    return pd.Series(values, dtype=storage)


def prepare_csv(
    payload: bytes,
    options: dict,
    columns: list[dict],
    *,
    profile: str = "imported-csv",
    source_name: str = "source.csv",
    source_sha256: str | None = None,
    max_bytes: int = 64 * 1024 * 1024,
    max_rows: int = 100000,
) -> CsvPrepared:
    """Confirm declarations, normalize through the shared pipeline, and validate.

    The caller must retain the original payload alongside this receipt. No row is
    dropped for a missing or invalid value; conversion stops with its location.
    """
    parsed = _parse(payload, options, max_bytes, max_rows)
    if source_sha256 is not None and source_sha256 != parsed.sha256:
        raise DataValidationError("CSV source_sha256 differs from the confirmed preview")
    if not isinstance(source_name, str) or not source_name.strip():
        raise DataValidationError("CSV source_name must be a nonempty file name")
    declarations = _declarations(columns, parsed.names)
    included = [item for item in declarations if item["include"]]
    fields = tuple(
        FieldSchema(
            name=item["target"],
            dtype=item["dtype"],
            required=True,
            role=item["role"],
            unit=item["output_unit"],
        )
        for item in included
    )
    try:
        schema = load_schema(ProfileSchema(profile, "1.0", fields))
    except CPDataKitError as exc:
        raise DataValidationError(str(exc)) from exc
    frame = pd.DataFrame({item["target"]: _series(parsed, item) for item in included})
    source = Dataset(
        frame,
        {"units": {item["target"]: item["input_unit"] for item in included if item["input_unit"]}},
    )
    mappings = [
        FieldMapping(
            source=item["target"],
            target=item["target"],
            input_unit=item["input_unit"] if item["input_unit"] != item["output_unit"] else None,
            output_unit=item["output_unit"] if item["input_unit"] != item["output_unit"] else None,
            source_note=f"User confirmed CSV column {item['index'] + 1}: {item['source_name']}",
        )
        for item in included
    ]
    try:
        # The location-aware checks below turn overflow into an actionable error.
        with np.errstate(over="ignore", under="ignore", invalid="ignore"):
            value = normalize_dataset(source, schema, mappings, drop_unmapped=True)
    except (CPDataKitError, ValueError, TypeError) as exc:
        raise DataValidationError(f"CSV unit normalization failed: {exc}") from exc
    for item in included:
        if item["dtype"] not in ("float", "integer"):
            continue
        if item["input_unit"] == item["output_unit"]:
            continue
        integers = []
        values = value.data[item["target"]].tolist()
        for (line, cells), number in zip(parsed.rows, values, strict=True):
            token = cells[item["index"]]
            with localcontext() as context:
                context.prec = 80
                exact = (
                    _UREG.Quantity(
                        Decimal(_number_token(token, parsed.options["decimal"])), item["input_unit"]
                    )
                    .to(item["output_unit"])
                    .magnitude
                )
            if not math.isfinite(number) or (number == 0 and exact != 0):
                raise _cell_error(
                    line, item, token, "unit conversion overflows or underflows float64"
                )
            if item["dtype"] == "integer":
                if exact != exact.to_integral_value() or number != exact or abs(number) > 2**53:
                    raise _cell_error(line, item, token, "conversion is not an exact integer")
                integers.append(int(exact))
        if item["dtype"] == "integer":
            value.data[item["target"]] = pd.Series(integers, dtype="int64")
    validation = validate_dataset(value, schema)
    if not validation.valid:
        details = "; ".join(f"{issue.field}: {issue.message}" for issue in validation.errors[:5])
        raise DataValidationError(f"CSV validation failed: {details}")
    manifest = {
        "version": 1,
        "source_name": source_name,
        "source_sha256": parsed.sha256,
        "source_size_bytes": len(payload),
        "options": dict(parsed.options),
        "record_count": len(parsed.rows),
        "columns": declarations,
        "excluded_columns": [
            {"index": item["index"], "source_name": item["source_name"]}
            for item in declarations
            if not item["include"]
        ],
        "output_order": [item["target"] for item in included],
        "validation": validation.to_dict(),
    }
    value.metadata["provenance"] = {"csv_import": deepcopy(manifest)}
    return CsvPrepared(value, schema, manifest)
