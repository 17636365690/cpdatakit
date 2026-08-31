# Schema Diff and Explicit Migration Implementation Plan

> For agentic workers: use the repository's approved subagent or executing-plan workflow to implement this plan task-by-task. Steps use checkbox syntax for tracking.

Goal: Add deterministic schema-diff and compatibility classification tooling for the v0.4.0
schema-migration roadmap. This stage compares contracts and leaves data changes to a later
migration command.

Architecture: Keep schema validation and canonical hashing as the source of truth. Add a pure
schema_diff module that compares validated ProfileSchema objects and returns JSON-ready results.
Add the CLI renderer after accepting the API contract. Data migration and HDF5 rewrites are outside
this stage.

Tech Stack: Python 3.10+, dataclasses, JSON, existing schema helpers, pytest, Hypothesis, Ruff, and Hatchling.

Spec: docs/superpowers/specs/2026-08-31-schema-migration-design.md

## Global Constraints

- Compare canonical validated schemas; never infer renames, units, tensor order, stress/strain measures, orientations, or identifier semantics.
- Keep schema_to_dict(), schema_to_canonical_json(), schema_sha256(), HDF5 snapshots, and schema contract version 1.0 compatible.
- Classify field removal, requiredness, dtype, shape, components, units, ranges, index flags, conventions, profile, extension prefix, and version changes as breaking.
- Classify only optional-field additions, alias additions, and description-only changes as backward-compatible.
- Preserve source/target order and use the fixed property order from the approved specification.
- A breaking diff is normal comparison output. Malformed schemas still raise SchemaError.
- Set requires_explicit_data_mapping for removals/renames and unit or meaning changes. Optional
  additions leave it false.

---

### Task 1: Specify the pure diff result with failing tests

Files:
- Create: tests/test_schema_diff.py
- Test against: src/cpdatakit/schema.py

Interfaces:
- Consumes: two schema inputs accepted by validate_schema().
- Produces: expected behavior for diff_schemas(source, target) -> dict[str, Any].

- [ ] Step 1: Add identical-schema and deterministic-output tests

  Build a schema with nested conventions and assert classification == identical, equal source/target
  hashes, empty field changes, empty convention changes, and stable JSON serialization with sorted
  keys and no non-finite values.

- [ ] Step 2: Add compatible-change tests

  Assert that adding an optional field, adding an alias, and changing only a description each produce
  classification == backward-compatible and do not set requires_explicit_data_mapping.

- [ ] Step 3: Add breaking-change tests

  Parameterize removed field, newly required field, dtype, shape, components, unit, range, index,
  convention, extension-prefix, profile, and schema-version changes. Assert the field name and exact
  change labels are present and classification is breaking.

- [ ] Step 4: Add rename and malformed-input tests

  Change one field name and assert it appears in removed plus added, with
  requires_explicit_data_mapping == True. Pass malformed schema inputs and assert existing
  SchemaError behavior remains unchanged.

- [ ] Step 5: Run the focused tests before implementation

  Run: pytest tests/test_schema_diff.py -q
  Expected: collection/import failure because diff_schemas does not exist yet. Do not implement the
  module before observing this failure.

### Task 2: Implement and export schema diff

Files:
- Create: src/cpdatakit/schema_diff.py
- Modify: src/cpdatakit/__init__.py
- Test: tests/test_schema_diff.py

Interfaces:
- Produces diff_schemas(source, target) -> dict[str, Any].

- [ ] Step 1: Implement validated source/target summaries

  Call validate_schema() on both inputs, record profile, schema_version, and schema_sha256(), and
  compare canonical schema JSON for the identical fast path.

- [ ] Step 2: Implement ordered field comparison

  Walk source fields in source order and target fields in target order. Emit removed, added, and
  changed entries. For shared names, compare the fixed property sequence dtype, shape, components,
  unit, required, allow_missing, minimum, maximum, index, unique, aliases, role, description and
  record only changed labels.

- [ ] Step 3: Implement compatibility classification

  Return identical for equal canonical JSON. Return backward-compatible when every difference is an
  optional addition, alias addition, or description change. Classify all other differences as
  breaking. Set requires_explicit_data_mapping for field removals/renames or any unit/meaning
  change. Optional additions leave it false.

- [ ] Step 4: Export the function without importing a second schema implementation

  Add diff_schemas to the package-root import block and __all__. Keep the module independent of CLI
  and report rendering so callers can use it without side effects.

- [ ] Step 5: Run focused and compatibility tests

  Run: pytest tests/test_schema_diff.py tests/test_schema.py tests/test_io.py -q
  Run: ruff check src tests
  Expected: all existing schema/hash/HDF5 snapshot behavior remains green.

### Task 3: Add the non-destructive CLI comparison command

Files:
- Modify: src/cpdatakit/cli.py
- Create: tests/test_cli_schema_diff.py
- Modify: README.md, README.zh-CN.md, docs/schema-authoring.md, CHANGELOG.md

Interfaces:
- Adds: cpdatakit schema diff SOURCE TARGET [--format json|markdown] [--output PATH] [--force].

- [ ] Step 1: Add failing parser and output tests

  Cover JSON stdout/file output, deterministic Markdown, protected existing output, --force, a
  breaking result returning status 0, malformed schema returning status 2, and no modification to
  either source schema file.

- [ ] Step 2: Implement a thin nested parser/dispatcher

  Add a schema command parser with a required diff subcommand. Keep schema loading and diff logic out
  of the CLI; reuse existing output protection and canonical JSON behavior.

- [ ] Step 3: Implement fixed JSON/Markdown rendering

  JSON uses sorted keys, allow_nan=False, and one final newline. Markdown lists source/target
  summaries, classification, added/removed fields, changed properties, conventions, and the scope
  note without raw paths or record values.

- [ ] Step 4: Document the no-mutation boundary

  Explain that the command compares contracts only and does not migrate data, alter schemas, or
  rewrite HDF5 artifacts. Keep v0.4.0 roadmap wording consistent with the approved first slice.

### Task 4: Verify and hand off schema-diff work

Files:
- Read: all changed schema/CLI/test/docs files and the approved spec

- [ ] Step 1: Run the complete quality gate

  Run the full pytest suite with the 85% coverage gate, Ruff check, Ruff format check, reproducible
  builds, wheel smoke, and existing HDF5 benchmark commands.

- [ ] Step 2: Verify compatibility and safety

  Confirm legacy format-1.0 files still load, canonical snapshot hashes are unchanged, malformed
  schemas fail with SchemaError, and no raw data or absolute paths enter diff artifacts.

- [ ] Step 3: Stop before data migration

  Record the explicit source/target schema-version manifest requirements as a follow-up. Do not add
  automatic data migration until a real post-1.0 schema pair and domain-reviewed operations exist.
