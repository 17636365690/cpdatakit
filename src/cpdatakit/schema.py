"""Schema parsing and built-in profile access."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from importlib.resources import files
from pathlib import Path
from typing import Any, Literal

from .exceptions import SchemaError

SUPPORTED_SCHEMA_VERSION = "1.0"
SUPPORTED_PROFILES = {"curve", "point", "field2d"}


@dataclass(frozen=True, slots=True)
class FieldSchema:
    """Declarative constraints for one standard field."""

    name: str
    dtype: Literal["float", "integer", "string", "boolean"]
    required: bool = False
    shape: list[int] = field(default_factory=list)
    role: str = "custom"
    unit: str | None = None
    allow_missing: bool = False
    aliases: list[str] = field(default_factory=list)
    minimum: float | None = None
    maximum: float | None = None
    index: bool = False
    unique: bool = False
    description: str = ""


@dataclass(frozen=True, slots=True)
class ProfileSchema:
    """A versioned CPDataKit dataset contract."""

    profile: str
    schema_version: str
    fields: tuple[FieldSchema, ...]
    conventions: dict[str, Any] = field(default_factory=dict)
    extension_prefix: str = "user_"

    def field_map(self) -> dict[str, FieldSchema]:
        """Map standard names to definitions."""
        return {item.name: item for item in self.fields}


def _parse(payload: dict[str, Any]) -> ProfileSchema:
    try:
        profile = payload["profile"]
        version = str(payload["schema_version"])
        raw_fields = payload["fields"]
    except (KeyError, TypeError) as exc:
        raise SchemaError(f"Malformed schema: missing {exc.args[0]!r}") from exc
    if profile not in SUPPORTED_PROFILES:
        raise SchemaError(f"Unsupported profile {profile!r}")
    if version != SUPPORTED_SCHEMA_VERSION:
        raise SchemaError(
            f"Unsupported schema version {version!r}; supported: {SUPPORTED_SCHEMA_VERSION}"
        )
    if not isinstance(raw_fields, list) or not raw_fields:
        raise SchemaError("Schema 'fields' must be a non-empty list")
    try:
        parsed = tuple(FieldSchema(**entry) for entry in raw_fields)
    except (TypeError, ValueError) as exc:
        raise SchemaError(f"Invalid field definition: {exc}") from exc
    names = [item.name for item in parsed]
    if len(names) != len(set(names)):
        raise SchemaError("Schema contains duplicate standard field names")
    missing_units = [
        item.name for item in parsed if item.dtype in {"float", "integer"} and not item.unit
    ]
    if missing_units:
        raise SchemaError(
            "Numeric fields must declare a unit (use 'dimensionless' when appropriate): "
            f"{missing_units}"
        )
    return ProfileSchema(
        profile=profile,
        schema_version=version,
        fields=parsed,
        conventions=dict(payload.get("conventions", {})),
        extension_prefix=str(payload.get("extension_prefix", "user_")),
    )


def load_schema(schema: str | Path | ProfileSchema) -> ProfileSchema:
    """Load a built-in profile name or a JSON schema path."""
    if isinstance(schema, ProfileSchema):
        return schema
    path = Path(schema)
    if str(schema) in SUPPORTED_PROFILES and not path.exists():
        resource = files("cpdatakit.schemas").joinpath(f"{schema}.json")
        try:
            return _parse(json.loads(resource.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError) as exc:
            raise SchemaError(f"Cannot load built-in schema {schema!r}: {exc}") from exc
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise SchemaError(f"Schema path does not exist: {path}") from exc
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SchemaError(f"Cannot read schema {path}: {exc}") from exc
    return _parse(payload)
