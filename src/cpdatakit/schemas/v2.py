"""Schema 2.0 values and deterministic local composition."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..exceptions import SchemaV2Error

_DTYPES = {"float", "integer", "string", "boolean"}
_Source = Path | dict[str, Any]


def _json_copy(value: Any, *, label: str) -> Any:
    try:
        json.dumps(value, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise SchemaV2Error(f"{label} must be JSON-compatible") from exc
    return deepcopy(value)


def _required_text(payload: dict[str, Any], key: str, *, label: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise SchemaV2Error(f"{label} {key} must be a non-empty string")
    return value


def _parse_dims(raw: Any, *, label: str) -> tuple[str, ...]:
    if not isinstance(raw, list) or any(
        not isinstance(item, str) or not item.strip() for item in raw
    ):
        raise SchemaV2Error(f"{label} dims must be a list of non-empty strings")
    if len(raw) != len(set(raw)):
        raise SchemaV2Error(f"{label} contains duplicate dimensions")
    return tuple(raw)


def _parse_chunks(raw: Any, *, label: str) -> tuple[int, ...] | None:
    if raw is None:
        return None
    if not isinstance(raw, list) or any(
        isinstance(item, bool) or not isinstance(item, int) or item <= 0 for item in raw
    ):
        raise SchemaV2Error(f"{label} chunks must contain positive integers")
    return tuple(raw)


def _parse_unit(raw: Any, *, label: str, dtype: str) -> str | None:
    if "unit" not in raw:
        raise SchemaV2Error(f"{label} unit is required")
    unit = raw["unit"]
    if unit is not None and (not isinstance(unit, str) or not unit.strip()):
        raise SchemaV2Error(f"{label} unit must be a non-empty string or null")
    if dtype in {"float", "integer", "boolean"} and unit is None:
        raise SchemaV2Error(f"{label} numeric and boolean declarations require a unit")
    return unit


@dataclass(frozen=True, slots=True)
class DimensionV2:
    name: str
    length: int

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "length": self.length}


@dataclass(frozen=True, slots=True)
class CoordinateV2:
    name: str
    dims: tuple[str, ...]
    dtype: str
    unit: str | None
    attributes: dict[str, Any] = field(default_factory=dict)
    chunks: tuple[int, ...] | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "name": self.name,
            "dims": list(self.dims),
            "dtype": self.dtype,
            "unit": self.unit,
        }
        if self.attributes:
            result["attributes"] = deepcopy(self.attributes)
        if self.chunks is not None:
            result["chunks"] = list(self.chunks)
        return result


@dataclass(frozen=True, slots=True)
class VariableV2:
    name: str
    dims: tuple[str, ...]
    dtype: str
    unit: str | None
    role: str
    components: tuple[str, ...] = field(default_factory=tuple)
    attributes: dict[str, Any] = field(default_factory=dict)
    chunks: tuple[int, ...] | None = None

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "name": self.name,
            "dims": list(self.dims),
            "dtype": self.dtype,
            "unit": self.unit,
            "role": self.role,
        }
        if self.components:
            result["components"] = list(self.components)
        if self.attributes:
            result["attributes"] = deepcopy(self.attributes)
        if self.chunks is not None:
            result["chunks"] = list(self.chunks)
        return result


@dataclass(frozen=True, slots=True)
class SchemaV2:
    profile: str
    schema_version: str
    conventions: dict[str, Any] = field(default_factory=dict)
    dimensions: tuple[DimensionV2, ...] = field(default_factory=tuple)
    coordinates: tuple[CoordinateV2, ...] = field(default_factory=tuple)
    variables: tuple[VariableV2, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "profile": self.profile,
            "schema_version": self.schema_version,
        }
        if self.conventions:
            result["conventions"] = deepcopy(self.conventions)
        result["dimensions"] = [item.to_dict() for item in self.dimensions]
        result["coordinates"] = [item.to_dict() for item in self.coordinates]
        result["variables"] = [item.to_dict() for item in self.variables]
        return result


@dataclass(frozen=True, slots=True)
class ResolvedSchemaV2:
    """Resolved schema plus its source audit manifest and declaration order."""

    schema: SchemaV2
    source_manifest: tuple[str, ...]
    resolved_order: tuple[str, ...]

    @property
    def profile(self) -> str:
        return self.schema.profile

    @property
    def schema_version(self) -> str:
        return self.schema.schema_version

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "schema_version": self.schema_version,
            "source_manifest": list(self.source_manifest),
            "resolved_order": list(self.resolved_order),
            "resolved": self.schema.to_dict(),
        }


def _parse_dimension(raw: Any, *, label: str) -> DimensionV2:
    if not isinstance(raw, dict):
        raise SchemaV2Error(f"{label} dimension must be an object")
    name = _required_text(raw, "name", label=label)
    length = raw.get("length")
    if isinstance(length, bool) or not isinstance(length, int) or length <= 0:
        raise SchemaV2Error(f"{label} dimension {name!r} length must be a positive integer")
    return DimensionV2(name, length)


def _parse_coordinate(raw: Any, *, label: str) -> CoordinateV2:
    if not isinstance(raw, dict):
        raise SchemaV2Error(f"{label} coordinate must be an object")
    name = _required_text(raw, "name", label=label)
    dims = _parse_dims(raw.get("dims"), label=f"{label} coordinate {name!r}")
    dtype = _required_text(raw, "dtype", label=f"{label} coordinate {name!r}")
    if dtype not in _DTYPES:
        raise SchemaV2Error(f"{label} coordinate {name!r} has unsupported dtype {dtype!r}")
    unit = _parse_unit(raw, label=f"{label} coordinate {name!r}", dtype=dtype)
    attributes = raw.get("attributes", {})
    if not isinstance(attributes, dict):
        raise SchemaV2Error(f"{label} coordinate {name!r} attributes must be an object")
    chunks = _parse_chunks(raw.get("chunks"), label=f"{label} coordinate {name!r}")
    return CoordinateV2(name, dims, dtype, unit, _json_copy(attributes, label="attributes"), chunks)


def _parse_variable(raw: Any, *, label: str) -> VariableV2:
    if not isinstance(raw, dict):
        raise SchemaV2Error(f"{label} variable must be an object")
    name = _required_text(raw, "name", label=label)
    dims = _parse_dims(raw.get("dims"), label=f"{label} variable {name!r}")
    dtype = _required_text(raw, "dtype", label=f"{label} variable {name!r}")
    if dtype not in _DTYPES:
        raise SchemaV2Error(f"{label} variable {name!r} has unsupported dtype {dtype!r}")
    unit = _parse_unit(raw, label=f"{label} variable {name!r}", dtype=dtype)
    role = _required_text(raw, "role", label=f"{label} variable {name!r}")
    components = raw.get("components", [])
    if not isinstance(components, list) or any(
        not isinstance(item, str) or not item.strip() for item in components
    ):
        raise SchemaV2Error(f"{label} variable {name!r} components must be strings")
    if len(components) != len(set(components)):
        raise SchemaV2Error(f"{label} variable {name!r} has duplicate components")
    attributes = raw.get("attributes", {})
    if not isinstance(attributes, dict):
        raise SchemaV2Error(f"{label} variable {name!r} attributes must be an object")
    chunks = _parse_chunks(raw.get("chunks"), label=f"{label} variable {name!r}")
    return VariableV2(
        name,
        dims,
        dtype,
        unit,
        role,
        tuple(components),
        _json_copy(attributes, label="attributes"),
        chunks,
    )


def _parse_source(
    payload: dict[str, Any], *, label: str
) -> tuple[
    str,
    str,
    dict[str, Any],
    tuple[DimensionV2, ...],
    tuple[CoordinateV2, ...],
    tuple[VariableV2, ...],
    str | None,
    tuple[str, ...],
]:
    profile = _required_text(payload, "profile", label=label)
    version = _required_text(payload, "schema_version", label=label)
    if version != "2.0":
        raise SchemaV2Error(f"{label} schema_version must be '2.0'")
    conventions = payload.get("conventions", {})
    if not isinstance(conventions, dict):
        raise SchemaV2Error(f"{label} conventions must be an object")
    conventions = _json_copy(conventions, label="conventions")

    raw_dimensions = payload.get("dimensions", [])
    raw_coordinates = payload.get("coordinates", [])
    raw_variables = payload.get("variables", [])
    if not all(
        isinstance(items, list) for items in (raw_dimensions, raw_coordinates, raw_variables)
    ):
        raise SchemaV2Error(f"{label} dimensions, coordinates, and variables must be lists")
    dimensions = tuple(_parse_dimension(item, label=label) for item in raw_dimensions)
    coordinates = tuple(_parse_coordinate(item, label=label) for item in raw_coordinates)
    variables = tuple(_parse_variable(item, label=label) for item in raw_variables)
    for kind, items in (
        ("dimension", dimensions),
        ("coordinate", coordinates),
        ("variable", variables),
    ):
        names = [item.name for item in items]
        if len(names) != len(set(names)):
            raise SchemaV2Error(f"duplicate {kind} declaration")

    extends = payload.get("extends")
    if extends is not None and (not isinstance(extends, str) or not extends.strip()):
        raise SchemaV2Error(f"{label} extends must be a non-empty local source")
    raw_includes = payload.get("includes", [])
    if not isinstance(raw_includes, list) or any(
        not isinstance(item, str) or not item.strip() for item in raw_includes
    ):
        raise SchemaV2Error(f"{label} includes must be a list of non-empty local sources")
    if len(raw_includes) != len(set(raw_includes)):
        raise SchemaV2Error("duplicate variable declaration")
    return (
        profile,
        version,
        conventions,
        dimensions,
        coordinates,
        variables,
        extends,
        tuple(raw_includes),
    )


def _load_payload(source: _Source, *, label: str) -> tuple[dict[str, Any], Path | None, str | None]:
    if isinstance(source, dict):
        return deepcopy(source), None, None
    path = Path(source)
    if path.as_posix().startswith(("http://", "https://")):
        raise SchemaV2Error("HTTP schema sources are disabled by default")
    if not path.exists():
        raise SchemaV2Error(f"Schema source does not exist: {label}")
    if not path.is_file():
        raise SchemaV2Error(f"Schema source is not a file: {label}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SchemaV2Error(f"Cannot read schema source: {label}") from exc
    if not isinstance(payload, dict):
        raise SchemaV2Error(f"Schema source root must be an object: {label}")
    return payload, path.resolve(), path.name


def _reference_path(reference: str, *, parent: Path | None) -> Path:
    if reference.startswith(("http://", "https://")):
        raise SchemaV2Error("HTTP schema sources are disabled by default")
    if parent is None:
        raise SchemaV2Error(f"Relative schema source has no local parent: {reference}")
    return parent / reference


def _merge_items(target: dict[str, Any], items: tuple[Any, ...], kind: str) -> None:
    for item in items:
        existing = target.get(item.name)
        if existing is None:
            target[item.name] = item
        elif existing.to_dict() != item.to_dict():
            raise SchemaV2Error(f"incompatible {kind} override: {item.name}")


def resolve_schema_v2(source: Path | dict[str, Any]) -> ResolvedSchemaV2:
    """Resolve a schema 2.0 source and local composition deterministically."""

    profile: str | None = None
    version: str | None = None
    conventions: dict[str, Any] = {}
    dimensions: dict[str, DimensionV2] = {}
    coordinates: dict[str, CoordinateV2] = {}
    variables: dict[str, VariableV2] = {}
    manifest: list[str] = []
    stack: list[Path] = []

    def visit(current: _Source, *, is_root: bool, parent: Path | None, fallback_label: str) -> None:
        nonlocal profile, version, conventions
        payload, resolved_path, source_label = _load_payload(current, label=fallback_label)
        label = source_label or fallback_label
        if resolved_path is not None:
            if resolved_path in stack:
                raise SchemaV2Error("extends cycle")
            stack.append(resolved_path)
        try:
            (
                source_profile,
                source_version,
                source_conventions,
                source_dimensions,
                source_coordinates,
                source_variables,
                extends,
                includes,
            ) = _parse_source(payload, label=label)
            if profile is None:
                profile = source_profile
                version = source_version
            elif (source_profile, source_version) != (profile, version):
                raise SchemaV2Error(f"source {label} profile/schema_version does not match root")
            for key, value in source_conventions.items():
                if key in conventions and conventions[key] != value:
                    raise SchemaV2Error(f"incompatible convention override: {key}")
                conventions[key] = value

            has_declarations = bool(source_dimensions or source_coordinates or source_variables)
            if has_declarations and label not in manifest:
                manifest.append(label)
            elif has_declarations:
                raise SchemaV2Error(f"duplicate schema source: {label}")

            child_parent = resolved_path.parent if resolved_path is not None else parent
            if extends is not None:
                visit(
                    _reference_path(extends, parent=child_parent),
                    is_root=False,
                    parent=child_parent,
                    fallback_label=extends,
                )
            for include in includes:
                visit(
                    _reference_path(include, parent=child_parent),
                    is_root=False,
                    parent=child_parent,
                    fallback_label=include,
                )
            _merge_items(dimensions, source_dimensions, "dimension")
            _merge_items(coordinates, source_coordinates, "coordinate")
            _merge_items(variables, source_variables, "variable")
        finally:
            if resolved_path is not None:
                stack.pop()

    root_label = source.name if isinstance(source, Path) else "<memory>"
    visit(
        source,
        is_root=True,
        parent=source.parent if isinstance(source, Path) else None,
        fallback_label=root_label,
    )
    if profile is None or version is None:
        raise SchemaV2Error("Schema source did not declare a profile")
    dimension_values = tuple(dimensions.values())
    dimension_order = {item.name: index for index, item in enumerate(dimension_values)}
    for item in (*coordinates.values(), *variables.values()):
        if any(dimension not in dimensions for dimension in item.dims):
            raise SchemaV2Error(f"declaration {item.name!r} references a missing dimension")
    if set(coordinates).intersection(variables):
        name = sorted(set(coordinates).intersection(variables))[0]
        raise SchemaV2Error(f"declaration name collision: {name}")
    coordinate_values = tuple(
        sorted(
            coordinates.values(),
            key=lambda item: (
                0 if item.name in dimension_order else 1,
                dimension_order.get(item.name, len(dimension_order)),
            ),
        )
    )
    variable_values = tuple(variables.values())
    resolved = SchemaV2(
        profile,
        version,
        conventions,
        dimension_values,
        coordinate_values,
        variable_values,
    )
    resolved_order = tuple(
        [item.name for item in dimension_values]
        + [item.name for item in coordinate_values if item.name not in dimensions]
        + [item.name for item in variable_values]
    )
    return ResolvedSchemaV2(resolved, tuple(manifest), resolved_order)


def _contract(value: SchemaV2 | ResolvedSchemaV2 | dict[str, Any]) -> SchemaV2:
    if isinstance(value, ResolvedSchemaV2):
        return value.schema
    if isinstance(value, SchemaV2):
        return value
    if isinstance(value, dict) and isinstance(value.get("resolved"), dict):
        return _contract(value["resolved"])
    if isinstance(value, dict) and value.get("schema_version") == "2.0":
        return resolve_schema_v2(value).schema
    raise TypeError("schema_v2_canonical_json expects SchemaV2 or ResolvedSchemaV2")


def schema_v2_canonical_json(value: SchemaV2 | ResolvedSchemaV2 | dict[str, Any]) -> str:
    """Return compact canonical JSON for a resolved schema 2.0 contract."""

    return json.dumps(
        _contract(value).to_dict(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def schema_v2_sha256(value: SchemaV2 | ResolvedSchemaV2 | dict[str, Any]) -> str:
    """Return SHA-256 for the canonical resolved schema 2.0 contract."""

    return hashlib.sha256(schema_v2_canonical_json(value).encode("utf-8")).hexdigest()
