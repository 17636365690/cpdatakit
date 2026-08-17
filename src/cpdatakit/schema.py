"""Schema parsing and built-in profile access."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from importlib.resources import files
from pathlib import Path
from typing import Any, Literal

from .exceptions import SchemaError

SUPPORTED_SCHEMA_VERSION = "1.0"
SUPPORTED_PROFILES = {"curve", "point", "field2d"}
SUPPORTED_DTYPES = {"float", "integer", "string", "boolean"}


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


def _validate_field(item: FieldSchema) -> None:
    if not isinstance(item.name, str) or not item.name.strip():
        raise SchemaError("Field names must be non-empty strings")
    if not isinstance(item.dtype, str) or item.dtype not in SUPPORTED_DTYPES:
        raise SchemaError(
            f"Field {item.name!r} has unsupported dtype {item.dtype!r}; "
            f"supported: {sorted(SUPPORTED_DTYPES)}"
        )
    boolean_options = {
        "required": item.required,
        "allow_missing": item.allow_missing,
        "index": item.index,
        "unique": item.unique,
    }
    invalid_options = [
        name for name, value in boolean_options.items() if not isinstance(value, bool)
    ]
    if invalid_options:
        raise SchemaError(f"Field {item.name!r} options must be boolean: {sorted(invalid_options)}")
    if not isinstance(item.shape, list) or any(
        not isinstance(size, int) or isinstance(size, bool) or size <= 0 for size in item.shape
    ):
        raise SchemaError(f"Field {item.name!r} shape must be a list of positive integers")
    if item.shape and item.index:
        raise SchemaError(f"Index field {item.name!r} must be scalar")
    if not isinstance(item.aliases, list) or any(
        not isinstance(alias, str) or not alias.strip() for alias in item.aliases
    ):
        raise SchemaError(f"Field {item.name!r} aliases must be non-empty strings")
    if len(item.aliases) != len(set(item.aliases)):
        raise SchemaError(f"Field {item.name!r} contains duplicate aliases")
    if not isinstance(item.role, str) or not isinstance(item.description, str):
        raise SchemaError(f"Field {item.name!r} role and description must be strings")
    if item.unit is not None and (not isinstance(item.unit, str) or not item.unit.strip()):
        raise SchemaError(f"Field {item.name!r} unit must be a non-empty string or null")
    if item.dtype in {"float", "integer"} and not item.unit:
        raise SchemaError(
            f"Numeric fields must declare a unit (use 'dimensionless' when appropriate): "
            f"{item.name!r}"
        )
    for name, value in (("minimum", item.minimum), ("maximum", item.maximum)):
        if value is not None and (
            not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(value)
        ):
            raise SchemaError(f"Field {item.name!r} {name} must be a finite number or null")
    if item.dtype not in {"float", "integer"} and (
        item.minimum is not None or item.maximum is not None
    ):
        raise SchemaError(f"Only numeric field {item.name!r} may declare minimum or maximum")
    if item.minimum is not None and item.maximum is not None and item.minimum > item.maximum:
        raise SchemaError(f"Field {item.name!r} minimum exceeds maximum")


def _parse(payload: dict[str, Any]) -> ProfileSchema:
    if not isinstance(payload, dict):
        raise SchemaError("Schema root must be a JSON object")
    try:
        profile = payload["profile"]
        version = str(payload["schema_version"])
        raw_fields = payload["fields"]
    except (KeyError, TypeError) as exc:
        raise SchemaError(f"Malformed schema: missing {exc.args[0]!r}") from exc
    if not isinstance(profile, str) or profile not in SUPPORTED_PROFILES:
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
    for item in parsed:
        _validate_field(item)
    names = [item.name for item in parsed]
    if len(names) != len(set(names)):
        raise SchemaError("Schema contains duplicate standard field names")
    aliases = [alias for item in parsed for alias in item.aliases]
    if len([*names, *aliases]) != len(set([*names, *aliases])):
        raise SchemaError("Schema field names and aliases must be globally unique")
    conventions = payload.get("conventions", {})
    if not isinstance(conventions, dict):
        raise SchemaError("Schema 'conventions' must be an object")
    extension_prefix = payload.get("extension_prefix", "user_")
    if not isinstance(extension_prefix, str) or not extension_prefix:
        raise SchemaError("Schema 'extension_prefix' must be a non-empty string")
    return ProfileSchema(
        profile=profile,
        schema_version=version,
        fields=parsed,
        conventions=dict(conventions),
        extension_prefix=extension_prefix,
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
