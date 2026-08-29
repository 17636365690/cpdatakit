# HDF5 Schema Provenance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Embed a canonical complete schema and SHA-256 digest in every newly written CPDataKit HDF5 file while keeping legacy format-1.0 files readable.

**Architecture:** Add canonical serialization helpers at the schema boundary, then let the HDF5 writer store their exact output and let the HDF5 reader validate and recover it. Keep the HDF5 envelope marker at 1.0, treat the snapshot as an additive capability, and expose only a sanitized digest/URI summary through inspection.

**Tech Stack:** Python 3.10+, json, hashlib, pandas, NumPy, h5py, pytest, pytest-cov, Ruff, Hatchling.

**Spec:** docs/superpowers/specs/2026-08-29-hdf5-schema-provenance-design.md

## Global Constraints

- Keep HDF5 format_version equal to 1.0.
- New write_hdf5() outputs always contain schema_json and schema_sha256.
- Legacy format-1.0 files without snapshot attributes remain readable.
- schema_json is compact, sorted-key, UTF-8 canonical JSON with no trailing newline.
- schema_sha256 is lowercase SHA-256 over the canonical schema JSON UTF-8 bytes.
- schema_uri is optional, non-empty text, never fetched, and valid only with a complete snapshot.
- Snapshot validation failures raise DataReadError; invalid writer arguments fail before temporary output creation.
- No schema inference, migration, solver adapter, dependency, or data-layout changes.

### Task 1: Add failing canonicalization and snapshot tests

Files:
- Modify: tests/test_schema.py
- Modify: tests/test_io.py
- Modify: tests/test_inspection.py

Interfaces:
- Test public schema_to_canonical_json() and schema_sha256() helpers.
- Test write_hdf5(..., schema_uri=...) and load_hdf5() metadata recovery.
- Test inspect_hdf5_structure() snapshot summary.

- [ ] Step 1: Add canonical schema helper tests

Extend tests/test_schema.py imports with hashlib and the two new schema helpers. Add:

    def test_schema_canonical_json_and_hash_are_stable() -> None:
        schema = make_profile_schema(
            "point",
            [make_field_schema("value", "float", required=True, unit="MPa")],
            conventions={"z": ["last", "value"], "a": {"measure": "explicit"}},
        )
        canonical = schema_to_canonical_json(schema)

        assert canonical == schema_to_canonical_json(schema_to_dict(schema))
        assert canonical.startswith('{"conventions":')
        assert "\n" not in canonical
        assert canonical.endswith("}")
        assert schema_sha256(schema) == hashlib.sha256(canonical.encode("utf-8")).hexdigest()

This catches non-deterministic serialization, pretty-JSON storage, and a digest that is not computed from the canonical bytes.

- [ ] Step 2: Add failing HDF5 snapshot round-trip tests

Extend tests/test_io.py imports with schema_sha256, schema_to_canonical_json, and schema_to_dict. Add:

    def test_hdf5_roundtrip_embeds_and_recovers_schema_snapshot(
        curve: Dataset, tmp_path: Path
    ) -> None:
        schema = load_schema("curve")
        output = tmp_path / "snapshot.h5"
        uri = "https://example.org/cpdatakit/schema/curve-1.0.json"

        write_hdf5(
            curve,
            output,
            schema,
            validate_dataset(curve, schema),
            schema_uri=uri,
        )

        with h5py.File(output, "r") as handle:
            assert handle.attrs["format_version"] == "1.0"
            assert handle.attrs["schema_json"] == schema_to_canonical_json(schema)
            assert handle.attrs["schema_sha256"] == schema_sha256(schema)
            assert handle.attrs["schema_uri"] == uri

        loaded = load_hdf5(output)
        assert loaded.metadata["schema_snapshot"] == {
            "schema": schema_to_dict(schema),
            "sha256": schema_sha256(schema),
            "uri": uri,
        }

This fails before implementation because the writer has no schema_uri argument and stores no snapshot attributes.

- [ ] Step 3: Add failing integrity and partial-metadata tests

Add these tests to tests/test_io.py:

    @pytest.mark.parametrize(
        ("mutation", "message"),
        [
            ("json", "schema_json"),
            ("hash", "schema_sha256"),
            ("profile", "profile"),
        ],
    )
    def test_hdf5_rejects_tampered_schema_snapshot(
        curve: Dataset, tmp_path: Path, mutation: str, message: str
    ) -> None:
        schema = load_schema("curve")
        output = tmp_path / f"tampered-{mutation}.h5"
        write_hdf5(curve, output, schema, validate_dataset(curve, schema))

        with h5py.File(output, "r+") as handle:
            if mutation == "json":
                handle.attrs["schema_json"] = '{"profile":"curve","schema_version":"1.0","fields":[]}'
            elif mutation == "hash":
                handle.attrs["schema_sha256"] = "0" * 64
            else:
                handle.attrs["schema_json"] = schema_to_canonical_json(load_schema("point"))
                handle.attrs["schema_sha256"] = schema_sha256(load_schema("point"))

        with pytest.raises(DataReadError, match=message):
            load_hdf5(output)


    def test_hdf5_rejects_partial_schema_snapshot(tmp_path: Path) -> None:
        path = tmp_path / "partial-snapshot.h5"
        _write_minimal_cpdatakit_hdf5(
            path,
            {"schema_json": schema_to_canonical_json(load_schema("curve"))},
        )

        with pytest.raises(DataReadError, match="schema_json.*schema_sha256"):
            load_hdf5(path)


    def test_hdf5_rejects_uri_without_embedded_snapshot(tmp_path: Path) -> None:
        path = tmp_path / "uri-only.h5"
        _write_minimal_cpdatakit_hdf5(path, {"schema_uri": "https://example.org/schema.json"})

        with pytest.raises(DataReadError, match="schema_json.*schema_sha256"):
            load_hdf5(path)


    @pytest.mark.parametrize("schema_uri", ["", 7, True])
    def test_hdf5_rejects_invalid_schema_uri_before_temp_output(
        curve: Dataset, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, schema_uri: object
    ) -> None:
        schema = load_schema("curve")
        result = validate_dataset(curve, schema)
        output = tmp_path / "invalid-uri.h5"

        def fail_if_temp_created(*args: object, **kwargs: object) -> None:
            raise AssertionError("temporary output must not be created for invalid schema_uri")

        monkeypatch.setattr("cpdatakit.io.tempfile.mkstemp", fail_if_temp_created)
        with pytest.raises(ValueError, match="schema_uri"):
            write_hdf5(curve, output, schema, result, schema_uri=schema_uri)

        assert not output.exists()

The old writer ignores these attributes, so the tests fail with no exception or a missing keyword argument.

- [ ] Step 4: Add a failing inspection summary test

Add this test to tests/test_inspection.py:

    def test_inspect_hdf5_reports_schema_snapshot(
        curve: Dataset, tmp_path: Path
    ) -> None:
        from cpdatakit.io import write_hdf5

        schema = load_schema("curve")
        path = tmp_path / "inspect-snapshot.h5"
        write_hdf5(
            curve,
            path,
            schema,
            validate_dataset(curve, schema),
            schema_uri="https://example.org/schema.json",
        )

        result = inspect_hdf5_structure(path)

        assert result["hdf5"]["schema_snapshot"] == {
            "present": True,
            "sha256": schema_sha256(schema),
            "uri": "https://example.org/schema.json",
        }

This fails before implementation because inspection has no snapshot summary.

- [ ] Step 5: Run the new tests and verify the expected red state

    $env:PYTHONPATH = "src;.venv\Lib\site-packages"
    & 'C:\Users\LEGION\AppData\Roaming\uv\python\cpython-3.12.13-windows-x86_64-none\python.exe' -m pytest tests/test_schema.py tests/test_io.py tests/test_inspection.py -q

Expected: the canonical helper imports fail, write_hdf5 rejects schema_uri, and the inspection assertion has no snapshot key. Existing tests must remain collected and runnable.

- [ ] Step 6: Commit only the failing snapshot tests

    git add tests/test_schema.py tests/test_io.py tests/test_inspection.py
    git commit -m "test: specify HDF5 schema provenance"

### Task 2: Implement canonical schema serialization

Files:
- Modify: src/cpdatakit/schema.py
- Modify: src/cpdatakit/__init__.py
- Test: tests/test_schema.py

Interfaces:
- Produces schema_to_canonical_json(schema) -> str.
- Produces schema_sha256(schema) -> str.
- Preserves existing schema_to_json() human-readable output.

- [ ] Step 1: Add canonical serialization and digest helpers

Import hashlib in schema.py and add:

    def schema_to_canonical_json(
        schema: str | Path | ProfileSchema | Mapping[str, Any],
    ) -> str:
        """Return compact deterministic JSON for schema hashing and snapshots."""
        contract = validate_schema(schema)
        try:
            return json.dumps(
                schema_to_dict(contract),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            )
        except (TypeError, ValueError) as exc:
            raise SchemaError(f"Schema is not JSON serializable: {exc}") from exc


    def schema_sha256(
        schema: str | Path | ProfileSchema | Mapping[str, Any],
    ) -> str:
        """Return SHA-256 of the canonical schema JSON UTF-8 bytes."""
        return hashlib.sha256(schema_to_canonical_json(schema).encode("utf-8")).hexdigest()

- [ ] Step 2: Export the helpers from the package root

Add schema_to_canonical_json and schema_sha256 to the schema import block and __all__ in src/cpdatakit/__init__.py.

- [ ] Step 3: Run canonical tests and the existing schema tests

    $env:PYTHONPATH = "src;.venv\Lib\site-packages"
    & 'C:\Users\LEGION\AppData\Roaming\uv\python\cpython-3.12.13-windows-x86_64-none\python.exe' -m pytest tests/test_schema.py -q

Expected: the new deterministic/hash test and all existing schema tests pass.

- [ ] Step 4: Commit canonical helpers

    git add src/cpdatakit/schema.py src/cpdatakit/__init__.py tests/test_schema.py
    git commit -m "feat: add canonical schema hashing"

### Task 3: Embed and validate schema snapshots in HDF5

Files:
- Modify: src/cpdatakit/io/__init__.py
- Test: tests/test_io.py

Interfaces:
- Extends write_hdf5() with keyword-only schema_uri: str | None = None.
- load_hdf5() and iter_hdf5_chunks() recover validated metadata["schema_snapshot"] when present.
- Legacy format-1.0 HDF5 files with no snapshot attributes remain readable.

- [ ] Step 1: Add the snapshot parser below _required_json_object

Import SchemaError, schema_sha256, schema_to_canonical_json, schema_to_dict, and validate_schema. Add:

    def _read_schema_snapshot(
        handle: h5py.File, path: Path, profile: str, schema_version: str
    ) -> dict[str, Any] | None:
        core_names = ("schema_json", "schema_sha256")
        present = {name: name in handle.attrs for name in (*core_names, "schema_uri")}
        if not any(present.values()):
            return None
        if not all(present[name] for name in core_names):
            raise DataReadError(
                "HDF5 schema_json and schema_sha256 must be present together: "
                f"{path}"
            )
        schema_text = _required_text_attr(handle, "schema_json", path)
        try:
            payload = json.loads(schema_text)
        except json.JSONDecodeError as exc:
            raise DataReadError(
                f"Invalid HDF5 schema_json metadata: {path}: {exc.msg}"
            ) from exc
        if not isinstance(payload, dict):
            raise DataReadError(f"HDF5 schema_json must encode a JSON object: {path}")
        try:
            embedded = validate_schema(payload)
        except SchemaError as exc:
            raise DataReadError(f"Invalid embedded HDF5 schema_json: {path}: {exc}") from exc
        if embedded.profile != profile or embedded.schema_version != schema_version:
            raise DataReadError(
                "Embedded HDF5 schema profile/schema_version does not match root metadata: "
                f"{path}"
            )
        stored_hash = _required_text_attr(handle, "schema_sha256", path)
        if len(stored_hash) != 64 or any(
            character not in "0123456789abcdefABCDEF" for character in stored_hash
        ):
            raise DataReadError(f"Invalid HDF5 schema_sha256 digest: {path}")
        expected_hash = schema_sha256(embedded)
        if stored_hash.lower() != expected_hash:
            raise DataReadError(
                f"HDF5 schema_sha256 does not match schema_json: {path}"
            )
        snapshot: dict[str, Any] = {
            "schema": schema_to_dict(embedded),
            "sha256": expected_hash,
        }
        if present["schema_uri"]:
            snapshot["uri"] = _required_text_attr(handle, "schema_uri", path)
        return snapshot

The parser must not read or fetch schema_uri as a URL; it only preserves validated text.

- [ ] Step 2: Attach snapshots to the common HDF5 metadata reader

In _read_hdf5_metadata(), call _read_schema_snapshot(handle, path, profile, schema_version) after validating the existing root attributes. Add the returned mapping under metadata["schema_snapshot"] only when it is not None. Leave legacy metadata without that key.

- [ ] Step 3: Embed canonical snapshot data in write_hdf5()

Before temporary-file creation, validate schema_uri:

    if schema_uri is not None and (
        not isinstance(schema_uri, str) or not schema_uri.strip()
    ):
        raise ValueError("schema_uri must be a non-empty string or None")

Also compute:

    schema_json = schema_to_canonical_json(schema)
    schema_digest = schema_sha256(schema)

Add these attributes beside the existing root attributes:

    handle.attrs["schema_json"] = schema_json
    handle.attrs["schema_sha256"] = schema_digest
    if schema_uri is not None:
        handle.attrs["schema_uri"] = schema_uri

Keep format_version set to "1.0", atomic replacement, validation protection, chunking, units, mapping, provenance, and output overwrite behavior unchanged.

- [ ] Step 4: Run focused HDF5 tests and verify green

    $env:PYTHONPATH = "src;.venv\Lib\site-packages"
    & 'C:\Users\LEGION\AppData\Roaming\uv\python\cpython-3.12.13-windows-x86_64-none\python.exe' -m pytest tests/test_io.py -q

Expected: snapshot round-trip, tamper, partial metadata, URI validation, legacy HDF5, chunked reads, and existing write protections all pass.

- [ ] Step 5: Run full regression before inspection changes

    $env:PYTHONPATH = "src;.venv\Lib\site-packages"
    & 'C:\Users\LEGION\AppData\Roaming\uv\python\cpython-3.12.13-windows-x86_64-none\python.exe' -m pytest -q

Expected: all tests pass.

- [ ] Step 6: Commit HDF5 snapshot support

    git add src/cpdatakit/io/__init__.py tests/test_io.py
    git commit -m "feat: embed HDF5 schema snapshots"

### Task 4: Expose snapshot status through inspection

Files:
- Modify: src/cpdatakit/inspection.py
- Test: tests/test_inspection.py

Interfaces:
- Adds hdf5.schema_snapshot.present to native CPDataKit HDF5 inspection.
- Adds sha256 and optional uri only from the validated embedded snapshot.
- Does not include full raw records or fetch an external URI.

- [ ] Step 1: Add the sanitized summary after native HDF5 result construction

In _inspect_native_hdf5(), derive:

    snapshot = metadata.get("schema_snapshot")
    snapshot_summary: dict[str, Any] = {
        "present": isinstance(snapshot, Mapping),
    }
    if isinstance(snapshot, Mapping):
        snapshot_summary["sha256"] = _safe_text(snapshot.get("sha256"))
        if "uri" in snapshot:
            snapshot_summary["uri"] = _safe_text(snapshot["uri"])
    result["hdf5"]["schema_snapshot"] = snapshot_summary

The summary must be safe for JSON/report rendering, and legacy files must return present=false without changing their read status.

- [ ] Step 2: Run inspection tests

    $env:PYTHONPATH = "src;.venv\Lib\site-packages"
    & 'C:\Users\LEGION\AppData\Roaming\uv\python\cpython-3.12.13-windows-x86_64-none\python.exe' -m pytest tests/test_inspection.py tests/test_reporting.py tests/test_cli_inspect_report.py -q

Expected: the new snapshot summary and all existing inspection/report/CLI tests pass.

- [ ] Step 3: Commit inspection integration

    git add src/cpdatakit/inspection.py tests/test_inspection.py
    git commit -m "feat: show HDF5 schema provenance in inspection"

### Task 5: Document the snapshot contract

Files:
- Modify: docs/data-format.md
- Modify: docs/schema-authoring.md
- Modify: README.md
- Modify: README.zh-CN.md
- Modify: CHANGELOG.md

Interfaces:
- Documents schema_to_canonical_json(), schema_sha256(), schema_uri, legacy compatibility, and no URI fetching.

- [ ] Step 1: Update data-format.md HDF5 layout

Add a paragraph after the existing HDF5 metadata list:

    New files also embed schema_json, the compact canonical JSON representation of the complete
    validated schema, and schema_sha256, its lowercase SHA-256 digest over UTF-8 bytes. An optional
    schema_uri records an external reference but is never fetched. Readers validate the embedded
    schema and its digest. Legacy format-1.0 files without these additive attributes remain
    readable; partial snapshots are rejected.

- [ ] Step 2: Update schema-authoring.md

Add the following example after schema_to_json():

    from cpdatakit import schema_sha256, schema_to_canonical_json

    canonical = schema_to_canonical_json(schema)
    print(schema_sha256(schema))

State that this compact string is the HDF5 snapshot representation and that the hash is reproducible across runs.

- [ ] Step 3: Update both READMEs and the changelog

State that CPDataKit HDF5 now records the complete schema snapshot and hash while preserving format 1.0 compatibility. Mention that schema_uri is provenance only and external resources are not downloaded. Add an Unreleased Fixed entry describing schema_json/schema_sha256 and legacy-read compatibility.

- [ ] Step 4: Validate documentation and commit

    rg -n "schema_json|schema_sha256|schema_uri|canonical|legacy|format 1.0|format 1.0|不下载|兼容" docs/data-format.md docs/schema-authoring.md README.md README.zh-CN.md CHANGELOG.md
    git diff --check

Expected: all three attribute names and compatibility language are present; git diff --check emits no output.

    git add docs/data-format.md docs/schema-authoring.md README.md README.zh-CN.md CHANGELOG.md
    git commit -m "docs: describe HDF5 schema provenance"

### Task 6: Run quality gates and audit backward compatibility

Files:
- Modify only files required by a failing verification command; otherwise do not edit additional files.

- [ ] Step 1: Run the complete test and coverage gate

    $env:PYTHONPATH = "src;.venv\Lib\site-packages"
    & 'C:\Users\LEGION\AppData\Roaming\uv\python\cpython-3.12.13-windows-x86_64-none\python.exe' -m pytest --cov=cpdatakit --cov-report=term-missing --cov-fail-under=85

Expected: zero failures and total coverage at least 85%.

- [ ] Step 2: Run lint, format, and build

    .\.venv\Scripts\ruff.exe check .
    .\.venv\Scripts\ruff.exe format --check .
    $env:PYTHONPATH = "src;.venv\Lib\site-packages"
    & 'C:\Users\LEGION\AppData\Roaming\uv\python\cpython-3.12.13-windows-x86_64-none\python.exe' -m build

Expected: Ruff, format, and the existing cpdatakit-0.2.0 build pass.

- [ ] Step 3: Verify the public helpers and a real HDF5 snapshot

    $env:PYTHONPATH = "src;.venv\Lib\site-packages"
    & 'C:\Users\LEGION\AppData\Roaming\uv\python\cpython-3.12.13-windows-x86_64-none\python.exe' -c "import tempfile; from pathlib import Path; import cpdatakit; from cpdatakit.io import write_hdf5; from cpdatakit.model import Dataset; import pandas as pd; schema=cpdatakit.load_schema('curve'); dataset=Dataset(pd.DataFrame({'step':[0], 'strain':[0.0], 'stress':[0.0]})); result=cpdatakit.validate_dataset(dataset, schema); path=Path(tempfile.mkdtemp())/'snapshot.h5'; write_hdf5(dataset, path, schema, result); loaded=cpdatakit.load_hdf5(path); print(loaded.metadata['schema_snapshot']['sha256']); print(cpdatakit.schema_sha256(schema))"

Expected: the two printed digests are identical and load_hdf5() returns the embedded snapshot.

- [ ] Step 4: Audit diff and legacy behavior

    git diff --check
    git status --short
    git log --oneline -10
    git diff origin/codex/stability-performance-quality...HEAD --stat
    rg -n "format_version.*1\\.0|schema_json|schema_sha256|schema_uri|def write_hdf5|def load_hdf5|def iter_hdf5_chunks" src/cpdatakit docs README.md README.zh-CN.md CHANGELOG.md

Confirm that no dependency declaration, schema contract version, HDF5 format marker, solver adapter, or external network fetch was added, and that the legacy complete HDF5 fixtures still pass.

- [ ] Step 5: Report only fresh evidence

Report exact test/coverage counts, lint/format/build results, changed files, the additive format-1.0 compatibility decision, and the remaining Surfalex public-data case as a separate follow-up.
