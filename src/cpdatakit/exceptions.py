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


class NormalizationError(CPDataKitError):
    """Raised when an explicit mapping fails validation or conversion."""


class OutputExistsError(CPDataKitError):
    """Raised when an existing file needs explicit force before replacement."""
