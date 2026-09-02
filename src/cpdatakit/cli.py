"""Command-line interface for CPDataKit."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt

from . import __version__
from .comparison import compare_reports, write_comparison_bundle
from .exceptions import CPDataKitError
from .inspection import (
    inspect_dataset,
    render_inspection_json,
    render_inspection_text,
    sanitize_error_message,
    write_inspection,
)
from .io import load_dataset, write_hdf5
from .normalization import load_mapping_file, normalize_dataset
from .plotting import (
    plot_counts,
    plot_field2d,
    plot_histogram,
    plot_stress_strain,
    plot_xy,
    save_figure,
)
from .reporting import build_report, write_report
from .schema import load_schema
from .schema_diff import (
    diff_schemas,
    render_schema_diff_json,
    render_schema_diff_markdown,
    write_schema_diff,
)
from .statistics import summarize_dataset
from .validation import validate_dataset


def _common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("data", type=Path, help="Input CSV, JSON records, or CPDataKit HDF5")
    parser.add_argument("--schema", required=True, help="Built-in profile or JSON schema path")
    parser.add_argument(
        "--mapping",
        type=Path,
        help="JSON file declaring explicit source/target fields and optional unit conversions",
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cpdatakit",
        description="Validate and process declared scientific and engineering data contracts.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument(
        "--debug", action="store_true", help="Show tracebacks for unexpected failures"
    )
    commands = parser.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate", help="Validate schema conformance")
    _common(validate)
    validate.add_argument("--json-output", type=Path, help="Write the validation report as JSON")
    validate.add_argument("--force", action="store_true", help="Replace an existing report")
    summary = commands.add_parser("summary", help="Print a descriptive JSON summary")
    _common(summary)
    summary.add_argument("--json-output", type=Path, help="Write the summary as JSON")
    summary.add_argument("--force", action="store_true", help="Replace an existing report")
    convert = commands.add_parser("convert", help="Convert to CPDataKit HDF5")
    _common(convert)
    convert.add_argument("--output", required=True, type=Path)
    convert.add_argument("--source-description")
    convert.add_argument("--force", action="store_true")
    plot = commands.add_parser("plot", help="Create a PNG or SVG plot")
    _common(plot)
    plot.add_argument(
        "--kind",
        required=True,
        choices=["stress-strain", "histogram", "grain-count", "phase-count", "field2d", "xy"],
    )
    plot.add_argument("--field", help="Declared numeric field for histogram")
    plot.add_argument("--x", help="Declared scalar numeric x-axis field for xy")
    plot.add_argument("--y", help="Declared scalar numeric y-axis field for xy")
    plot.add_argument("--output", required=True, type=Path)
    plot.add_argument("--force", action="store_true")
    inspect = commands.add_parser("inspect", help="Inspect a file and optionally check a schema")
    inspect.add_argument("data", type=Path, help="Input CSV, JSON records, or HDF5")
    inspect.add_argument("--schema", help="Optional built-in profile or JSON schema path")
    inspect.add_argument("--format", choices=["text", "json"], default="text")
    inspect.add_argument("--output", type=Path, help="Write the inspection result to a file")
    inspect.add_argument("--force", action="store_true", help="Replace an existing output")
    report = commands.add_parser("report", help="Write an offline validation report")
    report.add_argument("data", type=Path, help="Input CSV, JSON records, or HDF5")
    report.add_argument("--schema", required=True, help="Built-in profile or JSON schema path")
    report.add_argument("--format", choices=["html", "markdown", "json"], default="html")
    report.add_argument("--output", required=True, type=Path)
    report.add_argument("--force", action="store_true", help="Replace an existing output")
    compare = commands.add_parser("compare", help="Compare two JSON validation reports")
    compare.add_argument("left", type=Path, help="Left JSON report")
    compare.add_argument("right", type=Path, help="Right JSON report")
    compare.add_argument("--output", required=True, type=Path)
    compare.add_argument("--force", action="store_true", help="Replace an existing bundle")
    schema = commands.add_parser("schema", help="Compare schema contracts")
    schema_commands = schema.add_subparsers(dest="schema_command", required=True)
    schema_diff = schema_commands.add_parser("diff", help="Compare two schema contracts")
    schema_diff.add_argument("source", type=Path)
    schema_diff.add_argument("target", type=Path)
    schema_diff.add_argument("--format", choices=["json", "markdown"], default="json")
    schema_diff.add_argument("--output", type=Path)
    schema_diff.add_argument("--force", action="store_true", help="Replace an existing output")
    return parser


def _write_json(payload: dict[str, Any], target: Path | None, force: bool) -> None:
    rendered = json.dumps(payload, indent=2, sort_keys=True, allow_nan=False)
    if target is None:
        print(rendered)
        return
    if target.exists() and not force:
        raise CPDataKitError(f"Output already exists: {target}; pass --force to replace it")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(rendered + "\n", encoding="utf-8")


def _inspection_status(result: dict[str, Any]) -> int:
    schema = result.get("schema", {})
    validation = schema.get("validation", {}) if isinstance(schema, dict) else {}
    risks = result.get("risks", {})
    has_validation_errors = isinstance(validation, dict) and bool(validation.get("errors"))
    has_risks = isinstance(risks, dict) and bool(
        risks.get("missing_values") or risks.get("structural")
    )
    return 1 if has_validation_errors or has_risks else 0


def _run_inspect(args: argparse.Namespace) -> int:
    result = inspect_dataset(args.data, schema=args.schema)
    if args.output is None:
        rendered = (
            render_inspection_json(result)
            if args.format == "json"
            else render_inspection_text(result)
        )
        print(rendered, end="")
    else:
        write_inspection(result, args.output, format=args.format, force=args.force)
        print(args.output.name)
    return _inspection_status(result)


def _run_report(args: argparse.Namespace) -> int:
    report = build_report(args.data, args.schema)
    write_report(report, args.output, format=args.format, force=args.force)
    print(args.output.name)
    return 0 if report["validation"]["valid"] else 1


def _run_schema_diff(args: argparse.Namespace) -> int:
    diff = diff_schemas(args.source, args.target)
    if args.output is None:
        rendered = (
            render_schema_diff_json(diff)
            if args.format == "json"
            else render_schema_diff_markdown(diff)
        )
        print(rendered, end="")
    else:
        write_schema_diff(diff, args.output, format=args.format, force=args.force)
        print(args.output.name)
    return 0


def _read_report(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CPDataKitError(f"Report input does not exist: {path}") from exc
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CPDataKitError(f"Cannot read report input {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise CPDataKitError(f"Report input must be a JSON object: {path}")
    return payload


def _run_compare(args: argparse.Namespace) -> int:
    comparison = compare_reports(_read_report(args.left), _read_report(args.right))
    write_comparison_bundle(comparison, args.output, force=args.force)
    print(args.output)
    return 0


def _run(args: argparse.Namespace) -> int:
    if args.command == "compare":
        return _run_compare(args)
    if args.command == "schema":
        return _run_schema_diff(args)
    if args.command == "inspect":
        return _run_inspect(args)
    if args.command == "report":
        return _run_report(args)
    if args.command == "plot" and args.kind == "xy" and (not args.x or not args.y):
        raise CPDataKitError("--x and --y are required for xy")
    schema = load_schema(args.schema)
    dataset = load_dataset(args.data)
    if args.mapping is not None:
        mappings, drop_unmapped = load_mapping_file(args.mapping)
        dataset = normalize_dataset(
            dataset,
            schema,
            mappings,
            drop_unmapped=drop_unmapped,
        )
    result = validate_dataset(dataset, schema)
    if args.command == "validate":
        _write_json(result.to_dict(), args.json_output, args.force)
        return 0 if result.valid else 1
    if args.command == "summary":
        _write_json(
            summarize_dataset(dataset, schema, validation=result), args.json_output, args.force
        )
        return 0 if result.valid else 1
    if args.command == "convert":
        if not result.valid:
            print(json.dumps(result.to_dict(), indent=2), file=sys.stderr)
            return 1
        write_hdf5(
            dataset,
            args.output,
            schema,
            result,
            source_description=args.source_description,
            operation_log=["load", "validate", "convert"],
            force=args.force,
        )
        print(args.output)
        return 0
    if not result.valid:
        print(json.dumps(result.to_dict(), indent=2), file=sys.stderr)
        return 1
    if args.kind == "stress-strain":
        fig, _ = plot_stress_strain(dataset, schema)
    elif args.kind == "histogram":
        if not args.field:
            raise CPDataKitError("--field is required for histogram")
        fig, _ = plot_histogram(dataset, schema, args.field)
    elif args.kind == "grain-count":
        fig, _ = plot_counts(dataset, schema, "grain_id")
    elif args.kind == "phase-count":
        fig, _ = plot_counts(dataset, schema, "phase_id")
    elif args.kind == "field2d":
        fig, _ = plot_field2d(dataset, schema)
    else:
        fig, _ = plot_xy(dataset, schema, args.x, args.y)
    try:
        save_figure(fig, args.output, force=args.force)
    finally:
        plt.close(fig)
    print(args.output)
    return 0


def main(argv: list[str] | None = None) -> int:
    """Run the CLI and return a process exit status."""
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        return _run(args)
    except CPDataKitError as exc:
        if args.debug:
            raise
        parser.print_usage(sys.stderr)
        message = (
            sanitize_error_message(exc)
            if args.command in {"inspect", "report", "schema", "compare"}
            else str(exc)
        )
        print(f"{parser.prog}: error: {message}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
