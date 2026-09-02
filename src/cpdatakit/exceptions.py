"""Public exception hierarchy for CPDataKit."""


class CPDataKitError(Exception):
    """Base class for expected CPDataKit failures."""


class DataReadError(CPDataKitError):
    """Raised when an input fails a supported dataset reader."""


class DataValidationError(CPDataKitError):
    """Raised when invalid data is passed to a protected output operation."""


class AdapterError(CPDataKitError):
    """Raised when an external-format adapter fails to load its input safely."""


class SchemaError(CPDataKitError):
    """Raised when schema data fails validation or loading."""


class SchemaV2Error(SchemaError):
    """Raised when a schema 2.0 contract or local composition is invalid."""


class NormalizationError(CPDataKitError):
    """Raised when an explicit mapping fails validation or conversion."""


class OutputExistsError(CPDataKitError):
    """Raised when an existing file needs explicit force before replacement."""


class ScientificDataError(CPDataKitError):
    """Raised when an N-dimensional scientific value violates its data contract."""


class RaggedDataError(ScientificDataError):
    """Raised when a tabular array field has inconsistent per-record shapes."""


class AmbiguousRecordAxisError(ScientificDataError):
    """Raised when an N-dimensional value does not identify one record dimension."""


class UnsupportedDataError(ScientificDataError):
    """Raised when a value cannot be represented by the supported data model."""


class LossyConversionError(ScientificDataError):
    """Raised when a requested conversion would discard dimensions or coordinates."""


class CatalogError(CPDataKitError):
    """Raised when a local catalog or workspace boundary is invalid."""


class JobError(CPDataKitError):
    """Raised when a local in-process job cannot be addressed or scheduled."""
