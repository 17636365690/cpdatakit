"""CPDataKit public API."""

from ._version import __version__
from .io import load_dataset
from .normalization import FieldMapping, normalize_dataset
from .statistics import summarize_dataset
from .validation import validate_dataset

__all__ = [
    "FieldMapping",
    "__version__",
    "load_dataset",
    "normalize_dataset",
    "summarize_dataset",
    "validate_dataset",
]
