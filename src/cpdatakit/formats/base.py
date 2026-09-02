"""Format reader and writer protocols used by the v0.6 preflight."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, TypeAlias, runtime_checkable

DataValue: TypeAlias = object


@dataclass(frozen=True, slots=True)
class ReaderInfo:
    """Descriptive metadata for one reader implementation."""

    name: str
    format_name: str
    capabilities: frozenset[str]
    extensions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class WriterInfo:
    """Descriptive metadata for one writer implementation."""

    name: str
    format_name: str
    capabilities: frozenset[str]
    extensions: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DetectionResult:
    """Bounded format detection outcome."""

    matched: bool
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class CapabilityResult:
    """Whether a writer can represent a requested data value."""

    supported: bool
    messages: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "messages", tuple(self.messages))


@dataclass(frozen=True, slots=True)
class ReadLimits:
    """Explicit limits for bounded inspection and reads."""

    max_records: int = 10_000
    max_bytes: int = 64 * 1024 * 1024

    def __post_init__(self) -> None:
        for name in ("max_records", "max_bytes"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")


@dataclass(frozen=True, slots=True)
class Selection:
    """Optional fields and half-open record bounds for a reader."""

    fields: tuple[str, ...] = field(default_factory=tuple)
    start: int | None = None
    stop: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "fields", tuple(self.fields))
        for name in ("start", "stop"):
            value = getattr(self, name)
            if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
                raise ValueError(f"{name} must be an integer or None")
        if self.start is not None and self.start < 0:
            raise ValueError("start must be non-negative")
        if self.stop is not None and self.stop < 0:
            raise ValueError("stop must be non-negative")
        if self.start is not None and self.stop is not None and self.start > self.stop:
            raise ValueError("start must not exceed stop")


@runtime_checkable
class DatasetReader(Protocol):
    """Reader boundary shared by native and external format implementations."""

    info: ReaderInfo

    def detect(self, path: Path) -> DetectionResult:
        """Detect a representation using bounded reads."""

    def inspect(self, path: Path, *, limits: ReadLimits) -> Any:
        """Inspect structure without unbounded materialization."""

    def load(self, path: Path, *, selection: Selection | None = None) -> DataValue:
        """Load a selected data value."""


@runtime_checkable
class DatasetWriter(Protocol):
    """Writer boundary shared by native and external format implementations."""

    info: WriterInfo

    def check(self, data: DataValue) -> CapabilityResult:
        """Report representation capability before creating output."""

    def write(self, data: DataValue, output: Path, *, force: bool = False) -> Path:
        """Write a supported value atomically."""
