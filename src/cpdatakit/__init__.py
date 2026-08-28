"""CPDataKit public API."""

from ._version import __version__
from .io import iter_hdf5_chunks, load_dataset, load_hdf5
from .normalization import FieldMapping, load_mapping_file, normalize_dataset
from .schema import (
    FieldSchema,
    ProfileSchema,
    describe_schema,
    load_schema,
    make_field_schema,
    make_profile_schema,
    schema_to_dict,
    schema_to_json,
    validate_schema,
    write_schema,
)
from .statistics import summarize_dataset
from .validation import validate_dataset

__all__ = [
    "FieldMapping",
    "FieldSchema",
    "ProfileSchema",
    "__version__",
    "describe_schema",
    "iter_hdf5_chunks",
    "load_dataset",
    "load_hdf5",
    "load_mapping_file",
    "load_schema",
    "make_field_schema",
    "make_profile_schema",
    "normalize_dataset",
    "schema_to_dict",
    "schema_to_json",
    "summarize_dataset",
    "validate_dataset",
    "validate_schema",
    "write_schema",
]
