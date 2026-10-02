"""Metadata-only HDF5 read budgets and cooperative payload materialization."""

from math import prod

import h5py
import numpy as np

from .exceptions import DataReadError


def check_hdf5_budget(arrays, limits, *, selections=None, record_arrays=None):
    """Bound source records and estimated selected arrays before any payload read.

    max_bytes bounds an estimate of materialized array storage, not total process
    RSS. Callers must first run the self-contained-storage guard. Simple vlen
    strings use a conservative whole-file bound per selected entry; other object
    dtypes are rejected rather than treating pointer sizes as payload byte sizes.
    """
    if limits is None:
        return
    arrays = list(arrays)
    records = arrays if record_arrays is None else record_arrays
    if (
        max((array.shape[0] if array.shape else 1 for array in records), default=0)
        > limits.max_records
    ):
        raise DataReadError("HDF5 input exceeds the configured record limit")
    total = 0
    for array in arrays:
        indices = (selections or {}).get(array.name, (slice(None),) * array.ndim)
        shape = tuple(
            len(range(*index.indices(length)))
            for length, index in zip(array.shape, indices, strict=True)
        )
        count = prod(shape)
        if count and array.dtype.hasobject:
            string = h5py.check_string_dtype(array.dtype)
            if string is None or string.length is not None:
                raise DataReadError(
                    "HDF5 variable-length payload has no safe configured byte limit estimate"
                )
            # HDF5 stores VL string payloads in uncompressed file heaps; filters
            # apply to references, not the strings. A valid self-contained file
            # bounds each string by file size. Count every selection entry, even
            # repeated references/fill values; allow Unicode width and overhead.
            # https://support.hdfgroup.org/documentation/hdf5/latest/_view_tools_view.html
            # This estimate is not a native-parser sandbox for corrupt metadata.
            total += count * (4 * array.file.id.get_filesize() + 128)
        else:
            total += count * max(1, array.dtype.itemsize) * (4 if array.dtype.kind == "S" else 1)
        if total > limits.max_bytes:
            raise DataReadError("HDF5 materialized data exceeds the configured byte limit")


def read_hdf5_array(array, indices, *, context=None):
    """Read selected values with checkpoints between at most 10k-row/8MiB slabs.

    One selected first-axis row is the minimum slab. The returned array remains
    eager; cancellation discards it before any application output is published.
    """
    if context is None:
        return array[indices]
    context.checkpoint(f"read {array.name}")
    if not array.shape:
        values = array[()]
    else:
        ranges = [
            range(*index.indices(length))
            for length, index in zip(array.shape, indices, strict=True)
        ]
        shape = tuple(len(index) for index in ranges)
        values = np.empty(shape, dtype=array.dtype)
        row_bytes = max(1, prod(shape[1:]) * array.dtype.itemsize)
        step = max(1, min(10_000, 8 * 1024 * 1024 // row_bytes))
        first = ranges[0]
        for start in range(0, shape[0], step):
            stop = min(shape[0], start + step)
            context.checkpoint(f"read {array.name} {start}:{stop}/{shape[0]}")
            key = (
                slice(
                    first.start + start * first.step, first.start + stop * first.step, first.step
                ),
                *indices[1:],
            )
            values[start:stop] = array[key]
    context.checkpoint(f"read {array.name} complete")
    return values
