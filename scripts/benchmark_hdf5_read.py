"""Benchmark full, selected-field, and chunked CPDataKit HDF5 reads."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from cpdatakit.io import iter_hdf5_chunks, load_hdf5, write_hdf5
from cpdatakit.model import Dataset
from cpdatakit.schema import load_schema
from cpdatakit.validation import validate_dataset

try:
    import resource
except ImportError:  # pragma: no cover - resource is unavailable on Windows.
    resource = None


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be a positive integer")
    return parsed


def _peak_rss_mib() -> float | None:
    if resource is None:
        return None
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform == "darwin":
        return value / (1024 * 1024)
    return value / 1024


def _make_dataset(records: int) -> tuple[Dataset, Any]:
    schema = load_schema("curve")
    dataset = Dataset(
        pd.DataFrame(
            {
                "step": np.arange(records, dtype=np.int64),
                "strain": np.linspace(0.0, 0.02, records),
                "stress": np.linspace(0.0, 180.0, records),
            }
        ),
        {"units": {"step": "1", "strain": "1", "stress": "MPa"}},
    )
    return dataset, schema


def _measure(operation: Callable[[], object]) -> dict[str, object]:
    started = time.perf_counter()
    value = operation()
    elapsed = time.perf_counter() - started
    if isinstance(value, list):
        record_count = sum(len(item.data) for item in value)
    else:
        record_count = len(value.data)  # type: ignore[union-attr]
    return {
        "record_count": record_count,
        "elapsed_seconds": elapsed,
        "peak_rss_mib": _peak_rss_mib(),
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--records", type=_positive_int, default=100_000)
    parser.add_argument("--chunk-size", type=_positive_int, default=10_000)
    parser.add_argument("--hdf5-chunk-size", type=_positive_int, default=None)
    parser.add_argument("--output-dir", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    dataset, schema = _make_dataset(args.records)
    validation = validate_dataset(dataset, schema)
    if not validation.valid:
        raise RuntimeError("benchmark fixture failed schema validation")

    if args.output_dir is None:
        temporary = tempfile.TemporaryDirectory()
        directory = Path(temporary.name)
    else:
        temporary = None
        directory = args.output_dir
        directory.mkdir(parents=True, exist_ok=True)

    try:
        path = directory / "benchmark.h5"
        write_hdf5(
            dataset,
            path,
            schema,
            validation,
            force=True,
            hdf5_chunk_size=args.hdf5_chunk_size,
        )
        report = {
            "records": args.records,
            "chunk_size": args.chunk_size,
            "hdf5_chunk_size": args.hdf5_chunk_size,
            "full": _measure(lambda: load_hdf5(path)),
            "selected_fields": _measure(lambda: load_hdf5(path, fields=["step", "stress"])),
            "chunked": _measure(
                lambda: list(
                    iter_hdf5_chunks(path, fields=["step", "stress"], chunk_size=args.chunk_size)
                )
            ),
        }
        print(json.dumps(report, indent=2, sort_keys=True))
    finally:
        if temporary is not None:
            temporary.cleanup()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
