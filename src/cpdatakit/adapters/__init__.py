"""Extension interfaces; no solver-specific adapter is bundled in v0.1.0."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from ..model import Dataset


class DatasetAdapter(ABC):
    """Contract for optional, independently licensed source adapters."""

    @abstractmethod
    def load(self, path: Path) -> Dataset:
        """Translate an explicit external representation into a Dataset."""
