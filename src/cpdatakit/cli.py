"""Command-line interface for CPDataKit."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt

from . import __version__
from .exceptions import CPDataKitError
from .io import load_dataset, write_hdf5
from .normalization import load_mapping_file, normalize_dataset
from .plotting import (
    plot_counts,
    plot_field2d,
    plot_histogram,
    plot_stress_strain,
    save_figure,
)
from .schema import load_schema
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
        description="Validate and process declared crystal-plasticity data structures.",
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
        choices=["stress-strain", "histogram", "grain-count", "phase-count", "field2d"],
    )
    plot.add_argument("--field", help="Declared numeric field for histogram")
    plot.add_argument("--output", required=True, type=Path)
    plot.add_argument("--force", action="store_true")
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


def _run(args: argparse.Namespace) -> int:
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
    else:
        fig, _ = plot_field2d(dataset, schema)
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
        print(f"{parser.prog}: error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
