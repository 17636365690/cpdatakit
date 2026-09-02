"""Preflight reader and writer interfaces for future v0.6 format backends."""

from .base import (
    CapabilityResult,
    DatasetReader,
    DatasetWriter,
    DataValue,
    DetectionResult,
    ReaderInfo,
    ReadLimits,
    Selection,
    WriterInfo,
)
from .netcdf import NetCDFReader, NetCDFWriter
from .parquet import ParquetReader, ParquetWriter
from .zarr import ZarrReader, ZarrWriter

__all__ = [
    "CapabilityResult",
    "DataValue",
    "DatasetReader",
    "DatasetWriter",
    "DetectionResult",
    "NetCDFReader",
    "NetCDFWriter",
    "ParquetReader",
    "ParquetWriter",
    "ReadLimits",
    "ReaderInfo",
    "Selection",
    "WriterInfo",
    "ZarrReader",
    "ZarrWriter",
]
