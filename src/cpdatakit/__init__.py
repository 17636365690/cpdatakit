"""CPDataKit public API."""

from ._version import __version__
from .inspection import inspect_dataset, inspect_hdf5_structure
from .io import iter_hdf5_chunks, load_dataset, load_hdf5
from .normalization import FieldMapping, load_mapping_file, normalize_dataset
from .reporting import (
    build_report,
    render_report_html,
    render_report_json,
    render_report_markdown,
)
from .schema import (
    FieldSchema,
    ProfileSchema,
    describe_schema,
    load_schema,
    make_field_schema,
    make_profile_schema,
    schema_sha256,
    schema_to_canonical_json,
    schema_to_dict,
    schema_to_json,
    validate_schema,
    write_schema,
)
from .schema_diff import diff_schemas
from .statistics import summarize_dataset
from .validation import validate_dataset

__all__ = [
    "FieldMapping",
    "FieldSchema",
    "ProfileSchema",
    "__version__",
    "build_report",
    "describe_schema",
    "diff_schemas",
    "inspect_dataset",
    "inspect_hdf5_structure",
    "iter_hdf5_chunks",
    "load_dataset",
    "load_hdf5",
    "load_mapping_file",
    "load_schema",
    "make_field_schema",
    "make_profile_schema",
    "normalize_dataset",
    "render_report_html",
    "render_report_json",
    "render_report_markdown",
    "schema_sha256",
    "schema_to_canonical_json",
    "schema_to_dict",
    "schema_to_json",
    "summarize_dataset",
    "validate_dataset",
    "validate_schema",
    "write_schema",
]
