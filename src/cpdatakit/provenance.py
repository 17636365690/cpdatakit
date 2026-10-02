"""Reproducible provenance helpers."""

from __future__ import annotations

import hashlib
import json
import platform
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ._version import __version__
from .exceptions import DataReadError, DataValidationError

MAX_PROVENANCE_BYTES = 1024 * 1024
MAX_PROVENANCE_RECEIPTS = 64
MAX_PROVENANCE_DEPTH = 32


def _canonical(value: Any) -> bytes:
    """Bound portable JSON before hashing it or putting it in an artifact."""
    try:
        payload = json.dumps(
            value, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
        if len(payload) > MAX_PROVENANCE_BYTES:
            raise ValueError("provenance exceeds the 1 MiB size limit")
        pending = [(value, 0)]
        while pending:
            item, depth = pending.pop()
            if depth > MAX_PROVENANCE_DEPTH:
                raise ValueError("provenance exceeds the nesting depth limit")
            if isinstance(item, dict):
                if any(not isinstance(key, str) for key in item):
                    raise ValueError("provenance keys must be strings")
                pending.extend((entry, depth + 1) for entry in item.values())
            elif isinstance(item, list):
                pending.extend((entry, depth + 1) for entry in item)
            elif item is not None and type(item) not in (str, int, float, bool):
                raise ValueError("provenance must round-trip as JSON")
        return payload
    except (TypeError, ValueError, RecursionError, UnicodeError) as exc:
        raise DataValidationError(f"Invalid provenance: {exc}") from exc


def _receipt(payload: dict[str, Any]) -> dict[str, Any]:
    return {**payload, "sha256": hashlib.sha256(_canonical(payload)).hexdigest()}


def _operations(value: Any) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(step, str) for step in value):
        raise DataValidationError("Invalid provenance: operation_log must be a list of strings")
    return value


def validate_provenance(value: Any, *, reading: bool = False) -> dict[str, Any]:
    """Verify an optional flat receipt chain, preserving legacy metadata unchanged.

    Digests detect corruption and inconsistent edits; they are not signatures or
    evidence of authorship. Historical files without a chain remain readable.
    """
    try:
        if not isinstance(value, dict):
            raise DataValidationError("Invalid provenance: metadata must be an object")
        if "lineage" not in value:
            return deepcopy(value)
        _canonical(value)
        lineage = value["lineage"]
        if not isinstance(lineage, dict) or type(lineage.get("version")) is not int:
            raise DataValidationError("Invalid provenance lineage version")
        if lineage["version"] != 1:
            raise DataValidationError("Unsupported provenance lineage version")
        receipts = lineage.get("receipts")
        if not isinstance(receipts, list) or not 2 <= len(receipts) <= MAX_PROVENANCE_RECEIPTS:
            raise DataValidationError("Provenance receipt count exceeds limit or is incomplete")
        previous = None
        operations: list[str] = []
        origin: dict[str, Any] = {}
        for index, receipt in enumerate(receipts):
            if not isinstance(receipt, dict):
                raise DataValidationError("Invalid provenance receipt")
            payload = {key: entry for key, entry in receipt.items() if key != "sha256"}
            expected = hashlib.sha256(_canonical(payload)).hexdigest()
            if receipt.get("sha256") != expected:
                raise DataValidationError("Provenance receipt SHA-256 mismatch")
            if receipt.get("parent_sha256") != previous:
                raise DataValidationError("Provenance receipt parent SHA-256 mismatch")
            if index == 0:
                origin = receipt.get("provenance", {})
                if receipt.get("kind") != "origin" or not isinstance(origin, dict):
                    raise DataValidationError("Invalid provenance origin receipt")
                if "lineage" in origin:
                    raise DataValidationError("Provenance receipts must not nest prior lineage")
                operations.extend(_operations(origin.get("operation_log", [])))
            else:
                if receipt.get("kind") != "conversion":
                    raise DataValidationError("Invalid provenance conversion receipt")
                operations.extend(_operations(receipt.get("operation_log", [])))
            previous = expected
        if lineage.get("head_sha256") != previous:
            raise DataValidationError("Provenance lineage head SHA-256 mismatch")
        if value.get("operation_log") != operations:
            raise DataValidationError("Provenance operation_log differs from receipts")
        if value.get("csv_import") != origin.get("csv_import"):
            raise DataValidationError("Provenance CSV import differs from origin receipt")
        status = receipts[0].get("history_status")
        if status not in {"recorded_from_csv_import", "historical_unknown"}:
            raise DataValidationError("Invalid provenance origin history status")
        if value.get("history_status") != status:
            raise DataValidationError("Provenance history status differs from origin receipt")
        for key in (
            "input_filename",
            "input_sha256",
            "source_description",
            "converted_at_utc",
            "cpdatakit_version",
            "python_version",
        ):
            if value.get(key) != receipts[-1].get(key):
                raise DataValidationError(f"Provenance {key} differs from current receipt")
        return deepcopy(value)
    except DataValidationError as exc:
        if reading:
            raise DataReadError(str(exc)) from exc
        raise


def sha256_file(path: str | Path) -> str:
    """Compute a file's SHA-256 digest in streaming chunks."""
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_provenance(
    source: Path | None,
    *,
    source_description: str | None = None,
    operation_log: list[str] | None = None,
    parent_provenance: dict[str, Any] | None = None,
    schema_sha256: str | None = None,
    field_mapping: dict[str, str] | None = None,
    mapping_sha256: str | None = None,
    parameters: dict[str, Any] | None = None,
    input_sha256: str | None = None,
) -> dict[str, Any]:
    """Append a conversion receipt without copying a parent chain recursively.

    The completed output's digest belongs in the external job/catalog envelope,
    never inside the bytes being hashed. Input digests refer to complete parents.
    Limits reject a write rather than silently truncating older evidence.
    """
    parent = validate_provenance(parent_provenance if parent_provenance is not None else {})
    _canonical(parent)
    steps = _operations(operation_log if operation_log is not None else [])
    if parameters is not None and not isinstance(parameters, dict):
        raise DataValidationError("Invalid provenance: conversion parameters must be an object")
    current: dict[str, Any] = {
        "source_description": (
            source_description
            if source_description is not None
            else parent.get("source_description", "not provided")
        ),
        "converted_at_utc": datetime.now(UTC).isoformat(),
        "cpdatakit_version": __version__,
        "python_version": platform.python_version(),
        "operation_log": steps,
    }
    if source is not None:
        current["input_filename"] = source.name
        current["input_sha256"] = input_sha256 if input_sha256 is not None else sha256_file(source)
    else:
        current["input_filename"] = "not available"
        current["input_sha256"] = input_sha256 or "not available"
    if "lineage" in parent:
        receipts = parent["lineage"]["receipts"]
    else:
        origin = {key: value for key, value in parent.items() if key != "history_status"}
        manifest = origin.get("csv_import")
        status = (
            "recorded_from_csv_import"
            if isinstance(manifest, dict)
            and current["input_sha256"] != "not available"
            and manifest.get("source_sha256") == current["input_sha256"]
            else "historical_unknown"
        )
        receipts = [
            _receipt(
                {
                    "kind": "origin",
                    "parent_sha256": None,
                    "provenance": origin,
                    "history_status": status,
                }
            )
        ]
    if len(receipts) >= MAX_PROVENANCE_RECEIPTS:
        raise DataValidationError("Provenance exceeds the maximum receipt count limit (64)")
    mapping = field_mapping if field_mapping is not None else {}
    receipts.append(
        _receipt(
            {
                "kind": "conversion",
                "parent_sha256": receipts[-1]["sha256"],
                **current,
                "schema_sha256": schema_sha256,
                "field_mapping": mapping,
                "mapping_sha256": mapping_sha256 or hashlib.sha256(_canonical(mapping)).hexdigest(),
                "parameters": parameters or {},
            }
        )
    )
    result = {
        **parent,
        **current,
        "operation_log": [*_operations(parent.get("operation_log", [])), *steps],
        "history_status": receipts[0]["history_status"],
        "lineage": {"version": 1, "receipts": receipts, "head_sha256": receipts[-1]["sha256"]},
    }
    return validate_provenance(result)
