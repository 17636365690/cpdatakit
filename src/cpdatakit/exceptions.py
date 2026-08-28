"""Public exception hierarchy for CPDataKit."""


class CPDataKitError(Exception):
    """Base class for expected CPDataKit failures."""


class DataReadError(CPDataKitError):
    """Raised when an input cannot be read as a supported dataset."""


class DataValidationError(CPDataKitError):
    """Raised when invalid data is passed to a protected output operation."""


class SchemaError(CPDataKitError):
    """Raised when a schema is missing, malformed, or unsupported."""


class NormalizationError(CPDataKitError):
    """Raised when an explicit mapping cannot be applied safely."""


class OutputExistsError(CPDataKitError):
    """Raised when an operation would overwrite a file without consent."""
