# HDF5 Schema Provenance Design

**Date:** 2026-08-29  
**Status:** Approved in chat; implementation in progress

## Goal

Make newly written CPDataKit HDF5 files self-describing and auditable by embedding the exact
validated schema used for the conversion, while keeping existing format-1.0 files readable.

## Scope

This change covers:

1. Canonical schema JSON serialization and SHA-256 helpers.
2. HDF5 root attributes schema_json, schema_sha256, and optional schema_uri.
3. Writer-side embedding of the complete validated schema and reader-side hash verification.
4. Recovery of the embedded schema through load_hdf5() metadata.
5. Inspection/report metadata showing whether a snapshot is present and its digest.
6. Backward-compatible tests for legacy HDF5 files without a snapshot.
7. Data-format, API, README, and changelog documentation.

Out of scope: schema migration, external URI fetching, automatic schema selection, changes to
the schema contract version, solver adapters, and a new HDF5 storage layout.

## Format-version decision

The HDF5 envelope remains format_version == "1.0". The snapshot is an additive capability inside
the existing envelope: a newly written file always contains schema_json and schema_sha256, while
a legacy 1.0 file may contain neither. A file containing only part of the snapshot is malformed.
schema_uri is allowed only when the complete embedded snapshot is present.

This decision keeps new CPDataKit readers compatible with v0.2.0 files and lets v0.2.0 readers
ignore the additional attributes on newly written files. A future incompatible envelope change can
use HDF5 format version 1.1; this feature does not require that break.

## Canonical schema representation

The public helpers are:

    def schema_to_canonical_json(
        schema: str | Path | ProfileSchema | Mapping[str, Any],
    ) -> str

    def schema_sha256(
        schema: str | Path | ProfileSchema | Mapping[str, Any],
    ) -> str

schema_to_canonical_json() validates the schema, obtains schema_to_dict(), and serializes it with
UTF-8, sorted keys, compact separators, allow_nan=False, and no trailing newline:

    json.dumps(
        schema_to_dict(schema),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )

schema_sha256() hashes those exact UTF-8 bytes and returns lowercase hexadecimal SHA-256. Schema
JSON stored in HDF5 is this canonical string. Readers parse and validate the JSON, then recompute
the digest from the validated schema representation instead of trusting the raw attribute.

## HDF5 metadata contract

write_hdf5() gains one optional keyword:

    schema_uri: str | None = None

Every file produced by the writer stores:

- schema_json: canonical complete schema JSON;
- schema_sha256: digest of canonical schema JSON;
- schema_uri: an optional non-empty producer-supplied reference, never fetched by CPDataKit.

Readers require schema_json and schema_sha256 together when either is present. They validate that
the embedded schema is a JSON object, is accepted by the current schema parser, matches the root
profile and schema_version, and has the declared SHA-256. Invalid UTF-8, malformed JSON,
unsupported schemas, profile/version mismatches, invalid digests, and partial attributes raise
DataReadError.

load_hdf5() exposes a valid snapshot under:

    dataset.metadata["schema_snapshot"] == {
        "schema": schema_to_dict(embedded_schema),
        "sha256": "<lowercase hex digest>",
        # "uri": "...", when supplied
    }

Legacy files without snapshot attributes remain readable and simply do not contain the
schema_snapshot metadata key.

## Inspection and reporting

Native CPDataKit HDF5 inspection adds an hdf5.schema_snapshot summary containing present, sha256
when present, and uri when present. It does not fetch an external URI or replace an explicit schema
argument. Reports continue to validate against the caller-selected schema; the embedded snapshot
is provenance, not an implicit scientific inference.

## Error handling

- Invalid schema objects fail through the existing SchemaError boundary before writing.
- Invalid schema_uri values fail before a temporary HDF5 file is created.
- Snapshot parse, schema-validation, digest, and root-consistency failures raise DataReadError.
- Legacy format-1.0 files with no snapshot remain valid inputs.
- Atomic write, output-overwrite, validation, unit, and shaped-field semantics remain unchanged.

## Compatibility

The existing write_hdf5() positional and keyword arguments remain valid; schema_uri is keyword-only
and optional. The HDF5 root marker remains format_version="1.0", the eight existing metadata
attributes remain required, and no existing attribute changes meaning. CPDataKit v0.2.0 readers
ignore unknown snapshot attributes; current readers accept both legacy and snapshot-bearing 1.0
files.

## Test strategy

Tests will follow red-green-refactor:

- canonical schema JSON is deterministic and hashable;
- round-tripped HDF5 contains the exact canonical JSON and matching SHA-256;
- embedded schema metadata is recovered with profile/version and optional URI;
- tampered JSON, digest, profile, version, UTF-8, partial attributes, and URI placement fail;
- legacy complete format-1.0 files without snapshot attributes remain readable;
- inspection exposes snapshot presence/digest without materializing records;
- existing HDF5 read/write, atomicity, chunking, and CLI tests remain green.

## Documentation and acceptance criteria

docs/data-format.md, docs/schema-authoring.md, both READMEs, and CHANGELOG.md will document the
attributes, canonicalization, compatibility rule, and URI non-fetch behavior. Acceptance requires
the full test suite, coverage gate, Ruff, format check, build, and diff audit to pass, with no
dependency or solver-specific changes.
