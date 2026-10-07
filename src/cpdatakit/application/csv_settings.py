"""Reuse confirmed CSV declarations while keeping each source's facts separate."""

from __future__ import annotations

import json
from typing import Any

from ..exceptions import DataValidationError
from .csv_intake import _declarations, _options, preview_csv

_SIGNATURE_KEYS = ("index", "source_name", "dtype", "suggested_unit")
_COLUMN_KEYS = {
    "index",
    "source_name",
    "include",
    "target",
    "dtype",
    "role",
    "input_unit",
    "output_unit",
}
_REVIEW_WARNING = (
    "未写在 CSV 中的单位和实验事实无法自动核对。无表头文件的实际列顺序也无法核对。"
    "请逐文件核对来源后确认。"
)


def _validate_settings(settings: dict) -> tuple[dict, list[dict], list[dict] | None, bool]:
    if not isinstance(settings, dict):
        raise DataValidationError("导入设置必须是 JSON 对象。")
    try:
        size = len(json.dumps(settings, ensure_ascii=False, allow_nan=False))
    except (TypeError, ValueError, RecursionError) as exc:
        raise DataValidationError("导入设置包含无效内容。") from exc
    if size > 1024 * 1024:
        raise DataValidationError("导入设置过大。请减少字段数量。")
    if not isinstance(settings.get("options"), dict):
        raise DataValidationError("导入设置缺少有效的 options。")
    options = _options(settings["options"])
    columns = settings.get("columns")
    if not isinstance(columns, list) or not 0 < len(columns) <= 4096:
        raise DataValidationError("导入设置需要 1 至 4096 项列声明。")
    ignored = bool(set(settings) - {"options", "columns", "source_columns"})
    for column in columns:
        if not isinstance(column, dict):
            raise DataValidationError("导入设置的列声明必须是对象。")
        ignored |= bool(set(column) - _COLUMN_KEYS)
        for key in _COLUMN_KEYS:
            value = column.get(key)
            if isinstance(value, str) and len(value) > 4096:
                raise DataValidationError("导入设置的字段文本过长。")
    signature = settings.get("source_columns")
    if "source_columns" in settings:
        if not isinstance(signature, list) or len(signature) != len(columns):
            raise DataValidationError("原始列签名必须与列声明数量一致。")
        normalized = []
        for index, item in enumerate(signature):
            if (
                not isinstance(item, dict)
                or type(item.get("index")) is not int
                or item["index"] != index
                or not isinstance(item.get("source_name"), str)
                or len(item["source_name"]) > 4096
                or item.get("dtype") not in ("float", "integer", "string", "boolean")
                or "suggested_unit" not in item
                or (
                    item["suggested_unit"] is not None
                    and (
                        not isinstance(item["suggested_unit"], str)
                        or len(item["suggested_unit"]) > 4096
                    )
                )
            ):
                raise DataValidationError("原始列签名无效。请从已确认的导入重新保存设置。")
            ignored |= bool(set(item) - set(_SIGNATURE_KEYS))
            normalized.append({key: item[key] for key in _SIGNATURE_KEYS})
        signature = normalized
        names = [item["source_name"] for item in signature]
    else:
        # Legacy settings have no trustworthy cross-file signature. Validation
        # still uses the existing declaration contract, but never enables reuse.
        names = [f"column_{index + 1}" for index in range(len(columns))]
    declarations = _declarations(columns, names)
    return options, declarations, signature, ignored


def settings_from_csv(
    payload: bytes,
    options: dict,
    columns: list[dict],
    *,
    max_bytes: int = 64 * 1024 * 1024,
) -> dict:
    """Export only parsing, field declarations and the original column signature.

    The web caller verifies the saved source and manifest before calling this.
    Source hashes, samples and experiment descriptions are never included.
    """
    preview = preview_csv(payload, options, max_bytes=max_bytes)
    signature = [{key: column[key] for key in _SIGNATURE_KEYS} for column in preview["columns"]]
    settings = {"options": preview["options"], "columns": columns, "source_columns": signature}
    normalized_options, declarations, signature, _ = _validate_settings(settings)
    return {"options": normalized_options, "columns": declarations, "source_columns": signature}


def review_csv_settings(preview: dict, settings: dict) -> dict:
    """Compare saved settings to a fresh ``preview_csv`` result without applying changes."""
    options, declarations, signature, ignored = _validate_settings(settings)
    changes: list[dict[str, Any]] = []
    for key, value in options.items():
        if value != preview["options"][key]:
            changes.append(
                {"field": f"options.{key}", "before": value, "after": preview["options"][key]}
            )
    if signature is None:
        changes.append(
            {
                "field": "source_columns",
                "before": None,
                "after": "当前文件已预览。旧设置缺少原始列签名。需要重新确认声明。",
            }
        )
    else:
        current = preview["columns"]
        if len(signature) != len(current):
            changes.append(
                {"field": "source_columns.length", "before": len(signature), "after": len(current)}
            )
        for index in range(max(len(signature), len(current))):
            before = signature[index] if index < len(signature) else {}
            after = current[index] if index < len(current) else {}
            for key in _SIGNATURE_KEYS:
                if before.get(key) != after.get(key):
                    changes.append(
                        {
                            "field": f"source_columns[{index}].{key}",
                            "before": before.get(key),
                            "after": after.get(key),
                        }
                    )
    warnings = [_REVIEW_WARNING]
    if ignored:
        warnings.append("已忽略设置中的额外内容和文件级说明。它们不会被复制到本次导入。")
    if signature is None:
        warnings.append("旧设置没有原始列签名。不能自动复用列声明。请重新确认后保存新设置。")
    return {
        "matches": not changes,
        "changes": changes,
        "columns": declarations if not changes else [],
        "warnings": warnings,
    }
