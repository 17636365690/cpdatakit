"""Choose text-column storage before pandas can round integer values."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

import numpy as np
import pandas as pd

from ..data.scientific import _same_values
from ..exceptions import DataReadError

_INTEGER = re.compile(r"[+-]?[0-9]+\Z")
_NUMBER = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?\Z")


@dataclass(frozen=True, slots=True)
class _JsonNumber:
    token: str
    integer: bool


def _integer_value(token: str, field: str, record: int) -> int:
    try:
        value = int(token)
    except (ValueError, OverflowError) as exc:
        raise DataReadError(
            f"Field {field!r} record {record}: integer exceeds supported numeric precision"
        ) from exc
    if not -(2**63) <= value < 2**64:
        raise DataReadError(
            f"Field {field!r} record {record}: integer exceeds supported 64-bit precision"
        )
    return value


def _float_value(token: str, field: str, record: int) -> float:
    location = f"Field {field!r} record {record}"
    try:
        exact = Decimal(token)
        value = float(token)
    except (InvalidOperation, ValueError, OverflowError) as exc:
        raise DataReadError(
            f"{location}: numeric token exceeds supported float64 precision"
        ) from exc
    if not math.isfinite(value):
        raise DataReadError(f"{location}: numeric overflow outside float64")
    if value == 0 and exact != 0:
        raise DataReadError(
            f"{location}: numeric underflow would replace a nonzero value with zero"
        )
    if exact == exact.to_integral_value() and Decimal.from_float(value) != exact:
        raise DataReadError(f"{location}: integer precision would be lost in float64")
    return value


def _integer_series(values: list, name: str) -> pd.Series:
    present = [value for value in values if value is not None]
    minimum, maximum = min(present), max(present)
    if minimum < -(2**63) or maximum >= 2**64 or (minimum < 0 and maximum >= 2**63):
        raise DataReadError(f"Field {name!r}: integer range cannot be stored with 64-bit precision")
    unsigned = maximum >= 2**63
    nullable = len(present) != len(values)
    dtype = ("UInt64" if unsigned else "Int64") if nullable else ("uint64" if unsigned else "int64")
    return pd.Series(values, name=name, dtype=dtype)


def _numeric_series(values: list, name: str) -> pd.Series:
    present = [value for value in values if value is not None and not pd.isna(value)]
    if present and all(isinstance(value, int) and not isinstance(value, bool) for value in present):
        return _integer_series(
            [None if value is None or pd.isna(value) else value for value in values], name
        )
    floats = []
    for record, value in enumerate(values, 1):
        if value is None:
            floats.append(np.nan)
        elif isinstance(value, int):
            floats.append(_float_value(str(value), name, record))
        else:
            floats.append(value)
    return pd.Series(floats, name=name, dtype="float64")


def read_csv_frame(path: Path) -> pd.DataFrame:
    """Keep the ordinary CSV dialect/NA policy, but infer numbers losslessly."""
    tokens = pd.read_csv(path, dtype=object)
    if tokens.empty:
        raise DataReadError(f"CSV has no records: {path}")
    columns = {}
    for name in tokens:
        values = tokens[name].tolist()
        present = [value.strip() for value in values if isinstance(value, str)]
        if present and all(_INTEGER.fullmatch(value) for value in present):
            columns[name] = _integer_series(
                [
                    _integer_value(value, name, record) if isinstance(value, str) else None
                    for record, value in enumerate(values, 1)
                ],
                name,
            )
        elif present and all(
            _NUMBER.fullmatch(value)
            or value.lower() in {"inf", "+inf", "-inf", "infinity", "+infinity", "-infinity"}
            for value in present
        ):
            numbers = []
            for record, value in enumerate(values, 1):
                if not isinstance(value, str):
                    numbers.append(np.nan)
                elif _NUMBER.fullmatch(value.strip()):
                    numbers.append(_float_value(value.strip(), name, record))
                else:
                    # Explicit infinity remains a validation issue, not a parse overflow.
                    numbers.append(float(value))
            columns[name] = pd.Series(numbers, name=name, dtype="float64")
        elif present and all(
            value.lower() in {"true", "false"} for value in values if isinstance(value, str)
        ):
            columns[name] = pd.Series(
                [value.lower() == "true" if isinstance(value, str) else value for value in values],
                name=name,
            )
        else:
            columns[name] = pd.Series(values, name=name)
    for column in columns.values():
        column.index = tokens.index
    return pd.DataFrame(columns, index=tokens.index)


def _json_value(value: object, field: str, record: int) -> object:
    if isinstance(value, _JsonNumber):
        parse = _integer_value if value.integer else _float_value
        return parse(value.token, field, record)
    if isinstance(value, list):
        normalized = [_json_value(item, field, record) for item in value]
        try:
            array = np.asarray(normalized)
            original = np.asarray(normalized, dtype=object)
        except (ValueError, TypeError, OverflowError):
            # Existing shape validation diagnoses ragged arrays.
            return normalized
        if array.dtype.kind in "iuf" and not _same_values(original, array):
            raise DataReadError(f"Field {field!r} record {record}: array promotion loses precision")
        return normalized
    if isinstance(value, dict):
        return {key: _json_value(item, field, record) for key, item in value.items()}
    return value


def read_json_frame(path: Path) -> pd.DataFrame:
    """Parse JSON numbers exactly before deciding their column representation."""
    with path.open(encoding="utf-8") as stream:
        payload = json.load(
            stream,
            parse_float=lambda token: _JsonNumber(token, False),
            parse_int=lambda token: _JsonNumber(token, True),
        )
    if not isinstance(payload, list) or any(not isinstance(row, dict) for row in payload):
        raise DataReadError("JSON input must be an array of record objects")
    if not payload:
        raise DataReadError("JSON records input is empty")
    names = dict.fromkeys(name for row in payload for name in row)
    columns = {}
    for name in names:
        values = [_json_value(row.get(name), name, record) for record, row in enumerate(payload, 1)]
        if all(
            value is None or (isinstance(value, (int, float)) and not isinstance(value, bool))
            for value in values
        ):
            columns[name] = _numeric_series(values, name)
        else:
            columns[name] = pd.Series(values, name=name)
    return pd.DataFrame(columns, index=range(len(payload)))
