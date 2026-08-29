# Shaped Field Unit Conversion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend explicit FieldMapping unit conversion to scalar, vector, matrix, and higher-rank tensor fields while preserving declared shapes and existing APIs.

**Architecture:** Keep the public normalization boundary unchanged. Add private numeric-value conversion helpers in normalization.py that use the target FieldSchema.shape, convert each record with Pint, and return scalar values or one NumPy array per shaped record. Existing metadata and mapping-log updates remain in normalize_dataset().

**Tech Stack:** Python 3.10+, pandas, NumPy, Pint, pytest, pytest-cov, Ruff, Hatchling.

**Spec:** docs/superpowers/specs/2026-08-29-shaped-unit-conversion-design.md

## Global Constraints

- Keep normalize_dataset(dataset, schema, mappings, *, drop_unmapped=False) unchanged.
- Preserve source Dataset data and metadata; normalize only a defensive copy.
- Use the target schema's declared shape; never flatten or infer scientific meaning.
- Raise NormalizationError for malformed values, wrong shapes, non-numeric values, and unit conversion failures.
- Keep CPDataKit HDF5 format version 1.0 and all existing CLI/Python APIs compatible.
- Keep the dependency surface and behavior aligned with the existing solver-independent core.

### Task 1: Specify shaped conversion behavior with failing tests

Files:
- Modify: tests/test_normalization_statistics.py

Interfaces:
- Test the existing FieldMapping and normalize_dataset() interfaces.
- Use make_profile_schema() and make_field_schema() to declare a numeric target field with an exact shape.

- [ ] Step 1: Add shaped-schema helpers and valid conversion tests

Add NumPy and schema-authoring imports:

    import numpy as np
    from cpdatakit.schema import make_field_schema, make_profile_schema

Add this test-only helper:

    def _shaped_schema(shape: tuple[int, ...]):
        return make_profile_schema(
            "point",
            [make_field_schema("measure", "float", required=True, shape=shape, unit="MPa")],
        )

Add a parameterized test covering a vector, matrix, and rank-three tensor:

    @pytest.mark.parametrize(
        ("shape", "raw", "expected"),
        [
            ((2,), [[1_000_000.0, 2_000_000.0]], [[1.0, 2.0]]),
            (
                (2, 2),
                [[[1_000_000.0, 0.0], [0.0, 2_000_000.0]]],
                [[[1.0, 0.0], [0.0, 2.0]]],
            ),
            (
                (2, 1, 2),
                [[[[1_000_000.0, 0.0]], [[0.0, 2_000_000.0]]]],
                [[[[1.0, 0.0]], [[0.0, 2.0]]]],
            ),
        ],
    )
    def test_normalize_unit_conversion_preserves_shaped_values(
        shape: tuple[int, ...], raw: list[object], expected: list[object]
    ) -> None:
        source = Dataset(pd.DataFrame({"measure": raw}), {"units": {"measure": "Pa"}})

        result = normalize_dataset(
            source,
            _shaped_schema(shape),
            [FieldMapping("measure", "measure", "Pa", "MPa", "source specification")],
        )

        assert np.allclose(np.stack(result.data["measure"]), np.asarray(expected))
        assert all(np.asarray(value).shape == shape for value in result.data["measure"])
        assert all(np.asarray(value).dtype == np.dtype("float64") for value in result.data["measure"])
        assert result.metadata["units"]["measure"] == "MPa"
        assert result.metadata["field_mapping"]["measure"] == {
            "target": "measure",
            "input_unit": "Pa",
            "output_unit": "MPa",
            "source_note": "source specification",
        }
        assert source.data["measure"].iloc[0][0] == raw[0][0]
        assert source.metadata["units"]["measure"] == "Pa"

- [ ] Step 2: Add malformed-shape and non-numeric tests

Add tests whose messages require record context, declared shape, and regular-array wording:

    def test_normalize_rejects_wrong_shaped_record_with_position() -> None:
        source = Dataset(pd.DataFrame({"measure": [[[1.0, 2.0]]]}))

        with pytest.raises(
            NormalizationError, match=r"measure.*record 0.*expected shape \(2, 2\)"
        ):
            normalize_dataset(
                source,
                _shaped_schema((2, 2)),
                [FieldMapping("measure", "measure", "Pa", "MPa")],
            )


    def test_normalize_rejects_ragged_shaped_record_with_position() -> None:
        source = Dataset(pd.DataFrame({"measure": [[[1.0, 2.0], [3.0]]]}))

        with pytest.raises(
            NormalizationError, match=r"measure.*record 0.*regular numeric array"
        ):
            normalize_dataset(
                source,
                _shaped_schema((2, 2)),
                [FieldMapping("measure", "measure", "Pa", "MPa")],
            )


    def test_normalize_rejects_string_shaped_record_with_position() -> None:
        source = Dataset(pd.DataFrame({"measure": [["1", "2"]]}))

        with pytest.raises(NormalizationError, match=r"measure.*record 0.*numeric"):
            normalize_dataset(
                source,
                _shaped_schema((2,)),
                [FieldMapping("measure", "measure", "Pa", "MPa")],
            )

- [ ] Step 3: Run the normalization tests and verify the expected red state

Run:

    $env:PYTHONPATH = "src;.venv\Lib\site-packages"
    python -m pytest tests/test_normalization_statistics.py -q

Expected: the new valid shaped conversion test fails with NormalizationError: Field 'measure' is not numeric. The malformed tests fail their message assertions because the current implementation does not report record positions or declared shapes.

- [ ] Step 4: Commit only the failing tests

    git add tests/test_normalization_statistics.py
    git commit -m "test: specify shaped unit conversion"

### Task 2: Implement shape-preserving explicit conversion

Files:
- Modify: src/cpdatakit/normalization.py
- Test: tests/test_normalization_statistics.py

Interfaces:
- Consumes: ProfileSchema.field_map() and FieldMapping values from Task 1.
- Produces: a private conversion path used by normalize_dataset(); the public symbol set remains unchanged.

- [ ] Step 1: Add scalar-missing and numeric-array coercion helpers

Add NumPy to normalization.py and implement helpers below _UREG:

    def _is_missing_scalar(value: object) -> bool:
        if value is None:
            return True
        try:
            missing = pd.isna(value)
        except (TypeError, ValueError):
            return False
        return isinstance(missing, (bool, np.bool_)) and bool(missing)


    def _numeric_array(
        value: object, *, source: str, record: object, shape: tuple[int, ...]
    ) -> np.ndarray:
        try:
            array = np.asarray(value)
        except (TypeError, ValueError) as exc:
            raise NormalizationError(
                f"Field {source!r} record {record!r} is not a regular numeric array"
            ) from exc
        if tuple(array.shape) != shape:
            raise NormalizationError(
                f"Field {source!r} record {record!r} has shape {tuple(array.shape)}; "
                f"expected shape {shape}"
            )
        if array.dtype.kind not in {"i", "u", "f"}:
            raise NormalizationError(
                f"Field {source!r} record {record!r} is not numeric"
            )
        return np.asarray(array, dtype=np.float64)

The helper must reject booleans, complex values, strings, object arrays, and ragged arrays; it must not coerce numeric-looking strings.

- [ ] Step 2: Add the per-record Pint conversion helper

Implement this private helper below _numeric_array:

    def _convert_series_units(
        series: pd.Series,
        *,
        source: str,
        shape: tuple[int, ...],
        input_unit: str,
        output_unit: str,
    ) -> pd.Series:
        converted: list[object] = []
        for record, value in series.items():
            if _is_missing_scalar(value):
                converted.append(value)
                continue
            array = _numeric_array(value, source=source, record=record, shape=shape)
            try:
                magnitude = _UREG.Quantity(array, input_unit).to(output_unit).magnitude
            except (DimensionalityError, UndefinedUnitError) as exc:
                raise NormalizationError(
                    f"Cannot convert {source!r} from {input_unit!r} "
                    f"to {output_unit!r}: {exc}"
                ) from exc
            converted_array = np.asarray(magnitude, dtype=np.float64)
            converted.append(converted_array.item() if not shape else converted_array)
        return pd.Series(converted, index=series.index, name=series.name)

For shaped fields, the returned series contains one float64 NumPy array per record. For scalar fields, it is a normal numeric pandas series. Missing scalar records remain missing for the schema's existing validation policy.

- [ ] Step 3: Route mapping conversion through the target schema shape

Inside normalize_dataset(), resolve the target field definition before converting:

    spec = contract.field_map()[item.target]

Replace the current series.astype(float).to_numpy() block with:

    series = _convert_series_units(
        series,
        source=item.source,
        shape=spec.shape,
        input_unit=item.input_unit,
        output_unit=item.output_unit,
    )
    units[item.target] = item.output_unit

Keep the existing unit-pair check, target/source collision checks, source-column drop, target assignment, drop_unmapped behavior, and mapping-log code unchanged.

- [ ] Step 4: Run focused tests and verify green

    $env:PYTHONPATH = "src;.venv\Lib\site-packages"
    python -m pytest tests/test_normalization_statistics.py -q

Expected: all normalization tests pass, including scalar, vector, matrix, rank-three tensor, malformed-value, and source-isolation cases.

- [ ] Step 5: Run the full regression suite

    $env:PYTHONPATH = "src;.venv\Lib\site-packages"
    python -m pytest -q

Expected: the existing suite and new normalization tests pass without unrelated behavior changes.

- [ ] Step 6: Commit the implementation

    git add src/cpdatakit/normalization.py tests/test_normalization_statistics.py
    git commit -m "fix: support shaped unit conversion"

### Task 3: Document shaped unit conversion

Files:
- Modify: docs/data-format.md
- Modify: README.md
- Modify: README.zh-CN.md
- Modify: CHANGELOG.md

Interfaces:
- Documents the unchanged FieldMapping and normalize_dataset() APIs.
- States that conversion is elementwise over declared shaped fields and uses explicit conventions.

- [ ] Step 1: Update data-format.md

Extend the Unit and convention rules section with:

    When a mapping targets a declared vector, matrix, or tensor field, Pint converts each numeric
    element while preserving the complete per-record shape and trailing dimensions. Ragged arrays,
    wrong shapes, booleans, strings, complex values, and incompatible units are rejected. The mapping
    still must explicitly declare both input and output units; stress/strain measures, tensor
    component order, orientation representation, and identifier semantics come from the schema
    and mapping.

- [ ] Step 2: Update both README files

Update the normalization workflow bullet in README.md and README.zh-CN.md to state that explicit mappings convert scalar and shaped numeric fields elementwise while retaining vector/tensor shapes. Keep the existing explicit-convention guidance consistent.

- [ ] Step 3: Add the Unreleased changelog entry

Under Unreleased and Fixed in CHANGELOG.md, add:

    - Apply explicit Pint unit conversions to declared vector, matrix, and tensor fields without
      flattening their per-record shapes; malformed shaped values now fail with record context.

- [ ] Step 4: Check documentation and commit it

    rg -n "elementwise|vector|matrix|tensor|shape|incompatible units" docs/data-format.md README.md README.zh-CN.md CHANGELOG.md
    git diff --check

Expected: the new rule appears in all intended documentation locations and git diff --check emits no output.

    git add docs/data-format.md README.md README.zh-CN.md CHANGELOG.md
    git commit -m "docs: describe shaped unit conversion"

### Task 4: Run quality gates and audit the change

Files:
- Modify only files required by a failing verification command; otherwise do not edit additional files.

- [ ] Step 1: Run focused and full tests with coverage

    $env:PYTHONPATH = "src;.venv\Lib\site-packages"
    python -m pytest tests/test_normalization_statistics.py -q
    python -m pytest --cov=cpdatakit --cov-report=term-missing --cov-fail-under=85

Expected: focused and full suites pass, with total coverage at least 85%.

- [ ] Step 2: Run lint, format, and build checks

    .\.venv\Scripts\ruff.exe check .
    .\.venv\Scripts\ruff.exe format --check .
    $env:PYTHONPATH = "src;.venv\Lib\site-packages"
    python -m build

Expected: Ruff reports no errors, format check passes, and Hatchling builds the existing cpdatakit-0.2.0 distributions.

- [ ] Step 3: Audit compatibility and repository state

    git diff --check
    git status --short
    git log --oneline -6
    rg -n "def normalize_dataset|class FieldMapping|format_version|schema_json|hdf5" src/cpdatakit/normalization.py docs/data-format.md README.md README.zh-CN.md CHANGELOG.md

Confirm that the public normalization signature is unchanged, no HDF5 metadata or dependency declaration changed, no inference was introduced, and only the design, test, implementation, and documentation commits belong to this subproject.

- [ ] Step 4: Report only fresh evidence

Report the exact focused/full test counts, coverage percentage, Ruff/format/build exit results, changed files, and the remaining limitation that schema provenance and the Surfalex public-data case are separate follow-up subprojects.
