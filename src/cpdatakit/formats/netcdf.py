"""NetCDF reader and writer adapters backed by xarray."""

from __future__ import annotations

import importlib
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import h5py

from .._atomic import cleanup_staged_file, publish_file
from .._hdf5_safety import assert_self_contained_hdf5
from ..data import ScientificDataset
from ..exceptions import DataReadError, DataValidationError, OutputExistsError
from ._metadata import scientific_for_write, scientific_metadata
from ._selection import check_record_limit, describe_xarray, materialize_cf_selection
from .base import CapabilityResult, DetectionResult, ReaderInfo, ReadLimits, Selection, WriterInfo

_ENGINES = {"h5netcdf": "h5netcdf", "netcdf4": "netCDF4"}
_EXTENSIONS = (".nc", ".netcdf")


def _xarray() -> Any:
    try:
        return importlib.import_module("xarray")
    except Exception as exc:
        raise DataReadError(f"xarray is unavailable: {type(exc).__name__}") from exc


def _backend(engine: str) -> None:
    try:
        importlib.import_module(_ENGINES[engine])
    except Exception as exc:
        raise DataReadError(
            f"NetCDF engine {engine!r} is unavailable: {type(exc).__name__}"
        ) from exc


def _check_path(path: Path) -> None:
    if not path.exists():
        raise DataReadError(f"Input path does not exist: {path}")
    if not path.is_file():
        raise DataReadError(f"Input path is not a file: {path}")
    if path.suffix.lower() not in _EXTENSIONS:
        raise DataReadError(f"Unsupported NetCDF extension: {path.suffix}")


def _check_bytes(path: Path, limits: ReadLimits) -> None:
    if path.stat().st_size > limits.max_bytes:
        raise DataReadError("NetCDF input exceeds the configured byte limit")


def _metadata(dataset: Any, engine: str) -> dict[str, Any]:
    return scientific_metadata(dataset, format="NetCDF", engine=engine)


def _check_hdf5_storage(path: Path) -> None:
    """Check NetCDF4 containers before a backend can follow external storage."""
    try:
        if h5py.is_hdf5(path):
            with h5py.File(path, "r") as handle:
                assert_self_contained_hdf5(handle)
    except OSError as exc:
        raise DataReadError("Cannot verify NetCDF HDF5 storage") from exc


@contextmanager
def _backend_source(path: Path, engine: str, limits: ReadLimits | None, context=None):
    """Give the Windows C backend an ASCII snapshot without changing the source.

    Unlike a memory-buffer fallback, this releases all file handles even when the
    native parser rejects malformed input. The copy is streamed and exists only
    for the backend's context lifetime; Python and h5netcdf handle Unicode paths.
    """
    if os.name != "nt" or engine != "netcdf4" or str(path.absolute()).isascii():
        yield path
        return
    temporary_root = tempfile.gettempdir()
    if not temporary_root.isascii():
        # Short paths, when enabled, let a Unicode account use its existing temp
        # directory. Do not create a global directory or change environment state.
        import ctypes

        buffer = ctypes.create_unicode_buffer(32768)
        length = ctypes.windll.kernel32.GetShortPathNameW(temporary_root, buffer, len(buffer))
        if 0 < length < len(buffer) and buffer.value.isascii():
            temporary_root = buffer.value
        else:
            raise DataReadError(
                "The netCDF4 backend needs an ASCII temporary directory on Windows; "
                "choose an ASCII TEMP directory or use h5netcdf for NetCDF4 files."
            )
    with tempfile.TemporaryDirectory(prefix="cpdatakit-netcdf-", dir=temporary_root) as directory:
        native_path = Path(directory) / "input.nc"
        copied = 0
        with path.open("rb") as source, native_path.open("xb") as target:
            while True:
                if context is not None:
                    context.checkpoint("netcdf-path-copy")
                block = source.read(1024 * 1024)
                if not block:
                    break
                copied += len(block)
                if limits is not None and copied > limits.max_bytes:
                    raise DataReadError("NetCDF input exceeds the configured byte limit")
                target.write(block)
        _check_hdf5_storage(native_path)
        yield native_path


class NetCDFReader:
    """Read NetCDF files through one explicitly selected xarray engine."""

    def __init__(self, *, engine: str = "h5netcdf") -> None:
        if engine not in _ENGINES:
            raise ValueError(f"Unsupported NetCDF engine: {engine}")
        self.engine = engine
        self.info = ReaderInfo("netcdf", "NetCDF", frozenset({"scientific", "read"}), _EXTENSIONS)

    def detect(self, path: Path) -> DetectionResult:
        input_path = Path(path)
        if input_path.suffix.lower() not in _EXTENSIONS:
            return DetectionResult(False, "extension is not NetCDF")
        try:
            _xarray()
            _backend(self.engine)
        except DataReadError as exc:
            return DetectionResult(False, str(exc))
        return DetectionResult(True)

    def inspect(self, path: Path, *, limits: ReadLimits) -> dict[str, Any]:
        input_path = Path(path)
        _check_path(input_path)
        _check_bytes(input_path, limits)
        xarray = _xarray()
        _backend(self.engine)
        try:
            _check_hdf5_storage(input_path)
            with (
                _backend_source(input_path, self.engine, limits) as native_path,
                xarray.open_dataset(
                    native_path,
                    engine=self.engine,
                    create_default_indexes=False,
                    decode_times=False,
                    mask_and_scale=False,
                ) as dataset,
            ):
                dimensions = {name: int(length) for name, length in dataset.sizes.items()}
                data_variables = tuple(dataset.data_vars)
                record_count = (
                    int(dataset[data_variables[0]].sizes[dataset[data_variables[0]].dims[0]])
                    if data_variables and dataset[data_variables[0]].dims
                    else 0
                )
                if record_count > limits.max_records:
                    raise DataReadError("NetCDF input exceeds the configured record limit")
                return {
                    "format": "NetCDF",
                    "engine": self.engine,
                    "dimensions": dimensions,
                    "variables": describe_xarray(dataset, decode_cf=True),
                    "record_count": record_count,
                }
        except DataReadError:
            raise
        except (OSError, ValueError, TypeError) as exc:
            raise DataReadError(f"Cannot inspect NetCDF input {input_path}: {exc}") from exc

    def load(
        self,
        path: Path,
        *,
        selection: Selection | None = None,
        limits: ReadLimits | None = None,
        context=None,
    ) -> ScientificDataset:
        input_path = Path(path)
        _check_path(input_path)
        if limits is not None:
            _check_bytes(input_path, limits)
        xarray = _xarray()
        _backend(self.engine)
        try:
            _check_hdf5_storage(input_path)
            with (
                _backend_source(input_path, self.engine, limits, context) as native_path,
                xarray.open_dataset(
                    native_path,
                    engine=self.engine,
                    create_default_indexes=False,
                    decode_times=False,
                    mask_and_scale=False,
                ) as opened,
            ):
                check_record_limit(opened, limits, label="NetCDF", selection=selection)
                dataset = materialize_cf_selection(
                    opened, selection, label="NetCDF", context=context
                )
                if native_path != input_path:
                    # Only replace backend-generated source hints. Keep CF,
                    # dtype and shape encoding, and do not invent absent hints.
                    for encoding in [
                        dataset.encoding,
                        *(array.encoding for array in dataset.variables.values()),
                    ]:
                        if "source" in encoding:
                            encoding["source"] = str(input_path.absolute())
            metadata = _metadata(dataset, self.engine)
            return ScientificDataset(dataset, metadata, input_path)
        except DataReadError:
            raise
        except (OSError, ValueError, TypeError, KeyError) as exc:
            raise DataReadError(f"Cannot read NetCDF input {input_path}: {exc}") from exc


class NetCDFWriter:
    """Write ScientificDataset values through an explicit NetCDF engine."""

    def __init__(self, *, engine: str = "h5netcdf") -> None:
        if engine not in _ENGINES:
            raise ValueError(f"Unsupported NetCDF engine: {engine}")
        self.engine = engine
        self.info = WriterInfo("netcdf", "NetCDF", frozenset({"scientific", "write"}), _EXTENSIONS)

    def check(self, data: object) -> CapabilityResult:
        if not isinstance(data, ScientificDataset):
            return CapabilityResult(False, ("NetCDF requires a ScientificDataset",))
        try:
            _xarray()
            _backend(self.engine)
        except DataReadError as exc:
            return CapabilityResult(False, (str(exc),))
        for name, variable in data.data.variables.items():
            if variable.dtype.kind == "O":
                values = variable.values.flat
                if not all(isinstance(item, (str, bytes)) for item in values):
                    return CapabilityResult(
                        False, (f"variable {name!r} has unsupported object dtype",)
                    )
        try:
            scientific_for_write(data)
        except DataValidationError as exc:
            return CapabilityResult(False, (str(exc),))
        return CapabilityResult(True)

    def write(self, data: object, output: Path, *, force: bool = False) -> Path:
        capability = self.check(data)
        if not capability.supported:
            raise DataValidationError("; ".join(capability.messages))
        dataset = scientific_for_write(data)
        target = Path(output)
        if target.exists() and not force:
            raise OutputExistsError(
                f"Output already exists: {target}; pass force=True to replace it"
            )
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary: Path | None = None
        try:
            descriptor, name = tempfile.mkstemp(
                prefix=f".{target.name}.", suffix=target.suffix, dir=target.parent
            )
            os.close(descriptor)
            temporary = Path(name)
            dataset.to_netcdf(temporary, engine=self.engine)
            publish_file(temporary, target, force=force)
        except BaseException:
            if temporary is not None:
                cleanup_staged_file(temporary)
            raise
        return target
