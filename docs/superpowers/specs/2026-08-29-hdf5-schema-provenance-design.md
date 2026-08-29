# HDF5 Schema Provenance

**Date:** 2026-08-29  
**Status:** Approved in chat. Implementation in progress.

## Why the snapshot belongs in the file

The existing HDF5 metadata records the profile, schema version, units, mapping, provenance, and
validation summary. It needs the actual field definitions so a later reader can recover custom
fields, tensor shapes, component names, and conventions from the file.

New files will carry the exact validated schema used to write them. Old format-1.0 files will keep
working.

## Format version

The root format_version remains "1.0". The snapshot is an additive part of that format. A new
writer always stores schema_json and schema_sha256. A legacy file may have neither. If one of the
two appears without the other, the file is invalid. schema_uri is accepted only with both.

This keeps current readers able to open older files. A v0.2.0 reader ignores the extra attributes
when it opens a new file. A future incompatible envelope can use format version 1.1.

## Canonical schema JSON

The schema module exposes two helpers:

    def schema_to_canonical_json(
        schema: str | Path | ProfileSchema | Mapping[str, Any],
    ) -> str

    def schema_sha256(
        schema: str | Path | ProfileSchema | Mapping[str, Any],
    ) -> str

The first helper validates the schema, converts it with schema_to_dict(), and serializes it as
UTF-8 JSON with sorted keys, compact separators, allow_nan=False, and no trailing newline:

    json.dumps(
        schema_to_dict(schema),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )

The second helper hashes those UTF-8 bytes and returns lowercase hexadecimal SHA-256. The HDF5
writer stores the same canonical string in schema_json.

## HDF5 writer and reader

write_hdf5() gains the keyword-only argument:

    schema_uri: str | None = None

The writer checks that the URI is non-empty text, computes the canonical schema and digest before
creating a temporary file, then writes:

- schema_json
- schema_sha256
- schema_uri, when supplied

The reader accepts HDF5 strings and UTF-8 byte attributes. It parses and validates schema_json,
checks that the embedded profile and schema_version match the root attributes, and recomputes the
digest. It raises DataReadError for bad UTF-8, malformed JSON, an unsupported schema, a root
mismatch, a bad digest, or a partial snapshot. The caller controls access to schema_uri.

load_hdf5() returns the checked snapshot as:

    dataset.metadata["schema_snapshot"] == {
        "schema": schema_to_dict(embedded_schema),
        "sha256": "<lowercase hex digest>",
        # "uri": "...", when supplied
    }

A legacy file has no schema_snapshot key in its metadata.

## Inspection

Native HDF5 inspection reports hdf5.schema_snapshot.present. It includes the digest and URI when
they exist. The explicit schema argument remains authoritative for inspection. The snapshot records
provenance, while scientific choices come from the caller's selected contract.

## Compatibility and errors

Existing positional and keyword arguments to write_hdf5() remain valid. schema_uri is optional and
keyword-only. The eight existing metadata attributes keep their current meaning. The schema
contract version remains 1.0. This work keeps the existing schema, URI, storage-layout, adapter,
and dependency boundaries.

Schema errors raised before writing use SchemaError. Bad snapshot metadata read from a file uses
DataReadError. Atomic writes, overwrite protection, validation protection, chunking, and shaped
field handling stay as they are.

## Tests and docs

Tests cover deterministic canonical JSON, the hash, a round trip with an URI, tampering, profile
and version mismatches, partial attributes, bad digests, and legacy files. Inspection must show
the snapshot status without materializing raw records.

The data-format guide, schema-authoring guide, READMEs, and changelog will document the three
attributes, the hash rule, the compatibility behavior, and caller-managed URI access.
