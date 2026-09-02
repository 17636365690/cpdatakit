"""Base interface for optional CPDataKit source adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

from ..model import Dataset


@dataclass(frozen=True, slots=True)
class AdapterInfo:
    """Stable identity and capabilities for one dataset adapter class."""

    name: str
    format_name: str
    capabilities: frozenset[str]


class DatasetAdapter(ABC):
    """Contract for optional, independently licensed source adapters."""

    adapter_name: ClassVar[str | None] = None
    format_name: ClassVar[str | None] = None
    capabilities: ClassVar[frozenset[str]] = frozenset({"load"})

    @classmethod
    def info(cls) -> AdapterInfo:
        """Describe this adapter without constructing or loading it."""
        return AdapterInfo(
            name=cls.adapter_name or cls.__name__,
            format_name=cls.format_name or cls.__name__,
            capabilities=frozenset(cls.capabilities),
        )

    @classmethod
    def detect(cls, path: Path) -> bool:
        """Return whether a path appears to use this adapter's format."""
        return False

    @abstractmethod
    def load(self, path: Path) -> Dataset:
        """Translate an explicit external representation into a Dataset."""
