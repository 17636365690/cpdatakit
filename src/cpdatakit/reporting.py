"""Stable validation-report payloads and offline renderers."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from html import escape
from pathlib import Path
from typing import Any

from .adapters import DamaskDADF5Adapter
from .exceptions import CPDataKitError, OutputExistsError
from .inspection import inspect_dataset, sanitize_for_output
from .io import load_dataset
from .schema import ProfileSchema, load_schema, schema_to_dict
from .statistics import summarize_dataset
from .validation import validate_dataset

SCOPE_NOTE = "Validation conformance does not establish physical or scientific correctness."


def _has_non_finite(value: object) -> bool:
    if isinstance(value, bool) or value is None:
        return False
    if isinstance(value, (int, float)):
        return isinstance(value, float) and not math.isfinite(value)
    if isinstance(value, Mapping):
        return any(_has_non_finite(item) for item in value.values())
    if isinstance(value, (list, tuple, set, frozenset)):
        return any(_has_non_finite(item) for item in value)
    return False


def _safe_json_value(value: object) -> object:
    return sanitize_for_output(value)


def render_report_json(report: Mapping[str, Any]) -> str:
    """Render a report mapping as canonical JSON."""

    if _has_non_finite(report):
        raise ValueError("Report contains non-finite numeric values")
    return json.dumps(_safe_json_value(report), indent=2, sort_keys=True, allow_nan=False) + "\n"


def _cell(value: object) -> str:
    safe = _safe_json_value(value)
    if isinstance(safe, (dict, list)):
        text = json.dumps(safe, ensure_ascii=False, sort_keys=True, allow_nan=False)
    elif safe is None:
        text = "not available"
    else:
        text = str(safe)
    return text.replace("|", "\\|").replace("\r", " ").replace("\n", "<br>")


def _shape(value: object) -> str:
    safe = _safe_json_value(value)
    return json.dumps(safe, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _issue_lines(issues: object) -> list[str]:
    if not isinstance(issues, list) or not issues:
        return ["(none)"]
    lines = []
    for issue in issues:
        if isinstance(issue, Mapping):
            lines.append(
                "| "
                + " | ".join(
                    _cell(issue.get(key))
                    for key in ("code", "field", "message", "affected_records", "suggestion")
                )
                + " |"
            )
    return lines or ["(none)"]


def _mapping_block(value: object) -> str:
    safe = _safe_json_value(value)
    return json.dumps(safe, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)


def render_report_markdown(report: Mapping[str, Any]) -> str:
    """Render a report mapping as stable Markdown."""

    file_info = report.get("file", {})
    schema = report.get("schema", {})
    validation = report.get("validation", {})
    fields = report.get("fields", [])
    file_values = file_info if isinstance(file_info, Mapping) else {}
    validation_value = (
        _cell(validation.get("valid")) if isinstance(validation, Mapping) else "not available"
    )
    lines = [
        "# CPDataKit Validation Report",
        "",
        "## File and Format",
        "",
        f"- Filename: {_cell(file_values.get('filename'))}",
        f"- File type: {_cell(file_values.get('file_type'))}",
        f"- Format: {_cell(file_values.get('format'))}",
        f"- Format version: {_cell(file_values.get('format_version'))}",
        f"- Records: {_cell(report.get('record_count'))}",
        "",
        "## Schema",
        "",
    ]
    if isinstance(schema, Mapping):
        lines.extend(
            [
                f"- Profile: {_cell(schema.get('profile'))}",
                f"- Schema version: {_cell(schema.get('schema_version'))}",
                "",
            ]
        )
    else:
        lines.extend(["- not available", ""])
    lines.extend(
        [
            "## Fields",
            "",
            "| Field | Dtype | Shape | Unit | Missing | Description |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    if isinstance(fields, list) and fields:
        for field in fields:
            if not isinstance(field, Mapping):
                continue
            lines.append(
                "| "
                + " | ".join(
                    (
                        _cell(field.get("name")),
                        _cell(field.get("dtype")),
                        _shape(field.get("shape", [])),
                        _cell(field.get("unit")),
                        _cell(field.get("missing_count")),
                        _cell(field.get("description")),
                    )
                )
                + " |"
            )
    else:
        lines.append("| (none) | | | | | |")
    lines.extend(
        [
            "",
            "## Validation",
            "",
            f"- Valid: {validation_value}",
            "",
            "### Errors",
            "",
            "| Code | Field | Message | Affected records | Suggestion |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    lines.extend(_issue_lines(validation.get("errors") if isinstance(validation, Mapping) else []))
    lines.extend(
        [
            "",
            "### Warnings",
            "",
            "| Code | Field | Message | Affected records | Suggestion |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    lines.extend(
        _issue_lines(validation.get("warnings") if isinstance(validation, Mapping) else [])
    )
    lines.extend(
        [
            "",
            "## Descriptive Statistics",
            "",
            "~~~json",
            _mapping_block(report.get("statistics", {})),
            "~~~",
            "",
            "## Provenance",
            "",
            "~~~json",
            _mapping_block(report.get("provenance", {})),
            "~~~",
            "",
            "## Adapter",
            "",
            "~~~json",
            _mapping_block(report.get("adapter", {})),
            "~~~",
            "",
            "## HDF5 Storage",
            "",
            "~~~json",
            _mapping_block(report.get("hdf5", {})),
            "~~~",
            "",
            "## Scope",
            "",
            _cell(report.get("scope_note", SCOPE_NOTE)),
            "",
        ]
    )
    return "\n".join(lines)


def _html_value(value: object) -> str:
    safe = _safe_json_value(value)
    if isinstance(safe, (dict, list)):
        text = json.dumps(safe, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)
    elif safe is None:
        text = "not available"
    else:
        text = str(safe)
    return escape(text, quote=True)


def _html_definition_list(values: Mapping[str, Any]) -> str:
    parts = ["<dl>"]
    for key, value in values.items():
        parts.append(f"<dt>{_html_value(key)}</dt><dd>{_html_value(value)}</dd>")
    parts.append("</dl>")
    return "\n".join(parts)


def _html_issue_table(issues: object) -> str:
    parts = [
        "<table>",
        "<thead><tr><th>Code</th><th>Field</th><th>Message</th>"
        "<th>Affected records</th><th>Suggestion</th></tr></thead>",
        "<tbody>",
    ]
    if isinstance(issues, list) and issues:
        for issue in issues:
            issue = issue if isinstance(issue, Mapping) else {}
            parts.append(
                "<tr>"
                + "".join(
                    f"<td>{_html_value(issue.get(key))}</td>"
                    for key in ("code", "field", "message", "affected_records", "suggestion")
                )
                + "</tr>"
            )
    else:
        parts.append('<tr><td colspan="5">(none)</td></tr>')
    parts.extend(["</tbody>", "</table>"])
    return "\n".join(parts)


def render_report_html(report: Mapping[str, Any]) -> str:
    """Render a report mapping as self-contained, escaped HTML."""

    file_info = report.get("file", {})
    schema = report.get("schema", {})
    validation = report.get("validation", {})
    fields = report.get("fields", [])
    field_rows = []
    if isinstance(fields, list):
        for field in fields:
            field = field if isinstance(field, Mapping) else {}
            field_rows.append(
                "<tr>"
                + "".join(
                    f"<td>{_html_value(field.get(key))}</td>"
                    for key in ("name", "dtype", "shape", "unit", "missing_count", "description")
                )
                + "</tr>"
            )
    if not field_rows:
        field_rows.append('<tr><td colspan="6">(none)</td></tr>')
    file_values = file_info if isinstance(file_info, Mapping) else {}
    schema_values = schema if isinstance(schema, Mapping) else {}
    validation_values = validation if isinstance(validation, Mapping) else {}
    html = [
        "<!doctype html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        "<title>CPDataKit Validation Report</title>",
        "<style>",
        "body{font-family:Arial,sans-serif;color:#222;line-height:1.4;margin:2rem;}",
        "h1,h2,h3{color:#17365d;} table{border-collapse:collapse;width:100%;margin:1rem 0 2rem;}",
        "th,td{border:1px solid #9aa7b2;padding:.4rem;text-align:left;vertical-align:top;}",
        "th{background:#eaf0f5;} pre{white-space:pre-wrap;background:#f6f8fa;padding:1rem;}",
        "dt{font-weight:700;float:left;clear:left;width:12rem;}dd{margin-left:13rem;}",
        ".scope{border-left:.35rem solid #17365d;padding:.7rem 1rem;background:#f2f6fa;}",
        "@media print{body{margin:.5in;} h1,h2{break-after:avoid;} table{font-size:9pt;}}",
        "</style>",
        "</head>",
        "<body>",
        "<h1>CPDataKit Validation Report</h1>",
        "<h2>File and Format</h2>",
        _html_definition_list(
            {
                "Filename": file_values.get("filename"),
                "File type": file_values.get("file_type"),
                "Format": file_values.get("format"),
                "Format version": file_values.get("format_version"),
                "Records": report.get("record_count"),
            }
        ),
        "<h2>Schema</h2>",
        _html_definition_list(
            {
                "Profile": schema_values.get("profile"),
                "Schema version": schema_values.get("schema_version"),
            }
        ),
        "<h2>Fields</h2>",
        "<table><thead><tr><th>Field</th><th>Dtype</th><th>Shape</th>"
        "<th>Unit</th><th>Missing</th><th>Description</th></tr></thead>",
        "<tbody>",
        *field_rows,
        "</tbody></table>",
        "<h2>Validation</h2>",
        f"<p><strong>Valid:</strong> {_html_value(validation_values.get('valid'))}</p>",
        "<h3>Errors</h3>",
        _html_issue_table(validation_values.get("errors", [])),
        "<h3>Warnings</h3>",
        _html_issue_table(validation_values.get("warnings", [])),
        "<h2>Descriptive Statistics</h2>",
        f"<pre>{_html_value(report.get('statistics', {}))}</pre>",
        "<h2>Provenance</h2>",
        f"<pre>{_html_value(report.get('provenance', {}))}</pre>",
        "<h2>Adapter</h2>",
        f"<pre>{_html_value(report.get('adapter', {}))}</pre>",
        "<h2>HDF5 Storage</h2>",
        f"<pre>{_html_value(report.get('hdf5', {}))}</pre>",
        "<h2>Scope</h2>",
        f'<p class="scope">{_html_value(report.get("scope_note", SCOPE_NOTE))}</p>',
        "</body>",
        "</html>",
        "",
    ]
    return "\n".join(html)


def _load_for_report(path: Path, inspection: Mapping[str, Any]):
    if inspection.get("file", {}).get("format") == "DAMASK DADF5":
        return DamaskDADF5Adapter().load(path)
    return load_dataset(path)


def build_report(
    path: str | Path,
    schema: str | Path | ProfileSchema | Mapping[str, Any],
) -> dict[str, Any]:
    """Build a complete validation report for one input file."""

    input_path = Path(path)
    contract = load_schema(schema)
    inspection = inspect_dataset(input_path, schema=contract)
    dataset = _load_for_report(input_path, inspection)
    validation = validate_dataset(dataset, contract)
    statistics = summarize_dataset(dataset, contract, validation=validation)
    report = {
        "file": inspection.get("file", {}),
        "schema": schema_to_dict(contract),
        "record_count": inspection.get("record_count", len(dataset.data)),
        "fields": inspection.get("fields", []),
        "validation": validation.to_dict(),
        "statistics": statistics,
        "provenance": inspection.get("provenance", {}),
        "adapter": inspection.get("adapter", {}),
        "hdf5": inspection.get("hdf5", {}),
        "scope_note": SCOPE_NOTE,
    }
    return dict(_safe_json_value(report))


def write_report(
    report: Mapping[str, Any],
    output: str | Path,
    *,
    format: str = "html",
    force: bool = False,
) -> Path:
    """Write a report artifact without overwriting by default."""

    renderers = {
        "html": render_report_html,
        "markdown": render_report_markdown,
        "json": render_report_json,
    }
    try:
        renderer = renderers[format]
    except KeyError as exc:
        raise CPDataKitError(f"Unsupported report format: {format!r}") from exc
    rendered = renderer(report)
    target = Path(output)
    if target.exists() and not force:
        raise OutputExistsError(f"Output already exists: {target}; pass --force to replace it")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(rendered, encoding="utf-8")
    except OSError as exc:
        raise CPDataKitError(f"Cannot write report output {target}: {exc}") from exc
    return target
