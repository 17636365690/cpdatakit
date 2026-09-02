"""Optional external-format adapter interfaces and implementations."""

from .base import AdapterInfo, DatasetAdapter
from .damask_dadf5 import DamaskDADF5Adapter
from .registry import DEFAULT_ADAPTER_REGISTRY, AdapterRegistry

DEFAULT_ADAPTER_REGISTRY.register(DamaskDADF5Adapter)

__all__ = [
    "DEFAULT_ADAPTER_REGISTRY",
    "AdapterInfo",
    "AdapterRegistry",
    "DamaskDADF5Adapter",
    "DatasetAdapter",
]
