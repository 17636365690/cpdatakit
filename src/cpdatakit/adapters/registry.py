"""Lightweight in-process registration for external dataset adapters."""

from __future__ import annotations

from pathlib import Path

from ..exceptions import AdapterError
from .base import AdapterInfo, DatasetAdapter


class AdapterRegistry:
    """Register, describe, resolve, and detect adapter classes by stable name."""

    def __init__(self) -> None:
        self._adapters: dict[str, type[DatasetAdapter]] = {}

    def register(self, adapter: type[DatasetAdapter]) -> None:
        """Register one adapter class, rejecting invalid or duplicate identities."""
        if not isinstance(adapter, type) or not issubclass(adapter, DatasetAdapter):
            raise AdapterError("Registered adapter must be a DatasetAdapter subclass")
        info = adapter.info()
        if not info.name.strip() or not info.format_name.strip():
            raise AdapterError("Adapter name and format name must be non-empty")
        if info.name in self._adapters:
            raise AdapterError(f"Adapter name is already registered: {info.name}")
        self._adapters[info.name] = adapter

    def get(self, name: str) -> type[DatasetAdapter]:
        """Resolve a registered adapter class without constructing it."""
        try:
            return self._adapters[name]
        except KeyError as exc:
            raise AdapterError(f"Adapter is not registered: {name}") from exc

    def describe(self) -> tuple[AdapterInfo, ...]:
        """Return descriptors in deterministic registration order."""
        return tuple(adapter.info() for adapter in self._adapters.values())

    def detect(self, path: str | Path) -> tuple[type[DatasetAdapter], ...]:
        """Return every registered adapter whose explicit detector matches a path."""
        input_path = Path(path)
        return tuple(
            adapter
            for adapter in self._adapters.values()
            if "detect" in adapter.info().capabilities and adapter.detect(input_path)
        )


DEFAULT_ADAPTER_REGISTRY = AdapterRegistry()
