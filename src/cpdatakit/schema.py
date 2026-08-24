"""Schema parsing and built-in profile access."""

from __future__ import annotations

import json
import math
from collections.abc import Iterable, Mapping
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
    components: list[str] = field(default_factory=list)
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
    if not isinstance(item.components, list) or any(
        not isinstance(component, str) or not component.strip() for component in item.components
    ):
        raise SchemaError(f"Field {item.name!r} components must be non-empty strings")
    if len(item.components) != len(set(item.components)):
        raise SchemaError(f"Field {item.name!r} contains duplicate components")
    if item.components and not item.shape:
        raise SchemaError(f"Scalar field {item.name!r} cannot declare components")
    if item.components and len(item.components) != math.prod(item.shape):
        raise SchemaError(
            f"Field {item.name!r} declares {len(item.components)} components for shape "
            f"{item.shape}; expected {math.prod(item.shape)}"
        )
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


def _validate_profile(schema: ProfileSchema) -> ProfileSchema:
    if not isinstance(schema.profile, str) or schema.profile not in SUPPORTED_PROFILES:
        raise SchemaError(f"Unsupported profile {schema.profile!r}")
    if schema.schema_version != SUPPORTED_SCHEMA_VERSION:
        raise SchemaError(
            f"Unsupported schema version {schema.schema_version!r}; supported: "
            f"{SUPPORTED_SCHEMA_VERSION}"
        )
    if not isinstance(schema.fields, tuple) or not schema.fields:
        raise SchemaError("Schema 'fields' must be a non-empty tuple")
    for item in schema.fields:
        if not isinstance(item, FieldSchema):
            raise SchemaError("Schema fields must be FieldSchema objects")
        _validate_field(item)
    names = [item.name for item in schema.fields]
    if len(names) != len(set(names)):
        raise SchemaError("Schema contains duplicate standard field names")
    aliases = [alias for item in schema.fields for alias in item.aliases]
    if len([*names, *aliases]) != len(set([*names, *aliases])):
        raise SchemaError("Schema field names and aliases must be globally unique")
    if not isinstance(schema.conventions, dict):
        raise SchemaError("Schema 'conventions' must be an object")
    if not isinstance(schema.extension_prefix, str) or not schema.extension_prefix:
        raise SchemaError("Schema 'extension_prefix' must be a non-empty string")
    return schema


def _parse(payload: Mapping[str, Any]) -> ProfileSchema:
    if not isinstance(payload, dict):
        raise SchemaError("Schema root must be a JSON object")
    try:
        profile = payload["profile"]
        version = str(payload["schema_version"])
        raw_fields = payload["fields"]
    except (KeyError, TypeError) as exc:
        raise SchemaError(f"Malformed schema: missing {exc.args[0]!r}") from exc
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
    conventions = payload.get("conventions", {})
    if not isinstance(conventions, Mapping):
        raise SchemaError("Schema 'conventions' must be an object")
    extension_prefix = payload.get("extension_prefix", "user_")
    return _validate_profile(
        ProfileSchema(
            profile=profile,
            schema_version=version,
            fields=parsed,
            conventions=dict(conventions),
            extension_prefix=extension_prefix,
        )
    )


def make_field_schema(
    name: str,
    dtype: Literal["float", "integer", "string", "boolean"],
    *,
    required: bool = False,
    shape: Iterable[int] = (),
    components: Iterable[str] = (),
    role: str = "custom",
    unit: str | None = None,
    allow_missing: bool = False,
    aliases: Iterable[str] = (),
    minimum: float | None = None,
    maximum: float | None = None,
    index: bool = False,
    unique: bool = False,
    description: str = "",
) -> FieldSchema:
    """Create and immediately validate one declarative field definition."""
    item = FieldSchema(
        name=name,
        dtype=dtype,
        required=required,
        shape=list(shape),
        components=list(components),
        role=role,
        unit=unit,
        allow_missing=allow_missing,
        aliases=list(aliases),
        minimum=minimum,
        maximum=maximum,
        index=index,
        unique=unique,
        description=description,
    )
    _validate_field(item)
    return item


def make_profile_schema(
    profile: str,
    fields: Iterable[FieldSchema],
    *,
    schema_version: str = SUPPORTED_SCHEMA_VERSION,
    conventions: Mapping[str, Any] | None = None,
    extension_prefix: str = "user_",
) -> ProfileSchema:
    """Create and immediately validate a versioned profile contract."""
    schema = ProfileSchema(
        profile=profile,
        schema_version=schema_version,
        fields=tuple(fields),
        conventions=dict(conventions or {}),
        extension_prefix=extension_prefix,
    )
    return _validate_profile(schema)


def validate_schema(schema: str | Path | ProfileSchema | Mapping[str, Any]) -> ProfileSchema:
    """Validate a schema object, JSON mapping, built-in profile, or JSON path."""
    if isinstance(schema, ProfileSchema):
        return _validate_profile(schema)
    if isinstance(schema, Mapping):
        return _parse(schema)
    return load_schema(schema)


def schema_to_dict(schema: str | Path | ProfileSchema | Mapping[str, Any]) -> dict[str, Any]:
    """Return a validated schema as a JSON-serializable mapping."""
    contract = validate_schema(schema)
    return {
        "profile": contract.profile,
        "schema_version": contract.schema_version,
        "extension_prefix": contract.extension_prefix,
        "conventions": dict(contract.conventions),
        "fields": [
            {
                "name": item.name,
                "dtype": item.dtype,
                "required": item.required,
                "shape": list(item.shape),
                "components": list(item.components),
                "role": item.role,
                "unit": item.unit,
                "allow_missing": item.allow_missing,
                "aliases": list(item.aliases),
                "minimum": item.minimum,
                "maximum": item.maximum,
                "index": item.index,
                "unique": item.unique,
                "description": item.description,
            }
            for item in contract.fields
        ],
    }


def schema_to_json(
    schema: str | Path | ProfileSchema | Mapping[str, Any], *, indent: int = 2
) -> str:
    """Render a validated schema as canonical, human-readable JSON."""
    return json.dumps(schema_to_dict(schema), indent=indent, sort_keys=True) + "\n"


def write_schema(
    schema: str | Path | ProfileSchema | Mapping[str, Any],
    output: str | Path,
    *,
    force: bool = False,
) -> Path:
    """Write a validated schema JSON file without overwriting by default."""
    target = Path(output)
    if target.exists() and not force:
        raise SchemaError(f"Schema output already exists: {target}; pass force=True to replace it")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(schema_to_json(schema), encoding="utf-8")
    return target


def describe_schema(schema: str | Path | ProfileSchema | Mapping[str, Any]) -> str:
    """Return a concise Markdown description of a validated schema contract."""
    contract = validate_schema(schema)
    lines = [
        f"# {contract.profile} schema",
        "",
        f"- Schema version: `{contract.schema_version}`",
        f"- Extension prefix: `{contract.extension_prefix}`",
        "",
        "| Field | Dtype | Shape | Components | Unit | Required | Role |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for item in contract.fields:
        shape = "scalar" if not item.shape else " x ".join(map(str, item.shape))
        components = ", ".join(f"`{value}`" for value in item.components) or "—"
        required = "yes" if item.required else "no"
        lines.append(
            f"| `{item.name}` | `{item.dtype}` | `{shape}` | {components} | "
            f"`{item.unit or '—'}` | {required} | `{item.role}` |"
        )
    if contract.conventions:
        lines.extend(["", "## Conventions", ""])
        lines.extend(f"- `{key}`: {value}" for key, value in contract.conventions.items())
    return "\n".join(lines) + "\n"


def load_schema(schema: str | Path | ProfileSchema) -> ProfileSchema:
    """Load a built-in profile name or a JSON schema path."""
    if isinstance(schema, ProfileSchema):
        return _validate_profile(schema)
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
