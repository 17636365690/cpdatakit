"""Optional external-format adapter interfaces and implementations."""

from .base import DatasetAdapter
from .damask_dadf5 import DamaskDADF5Adapter

__all__ = ["DamaskDADF5Adapter", "DatasetAdapter"]
