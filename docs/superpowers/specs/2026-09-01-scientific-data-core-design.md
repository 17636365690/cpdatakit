# CPDataKit v0.5 Scientific Data Core Design

**Date:** 2026-09-01
**Status:** Awaiting maintainer approval; implementation must not begin before the maintainer replies
“批准 v0.5 设计”

## 1. Goal and positioning

CPDataKit v0.5 will position the project as a schema-first validation, normalization, and audit
tool for scientific and engineering data, originating from crystal-plasticity workflows. The goal
is not universal scientific-data support. The supported core remains a tabular record model with
scalar or fixed-shape per-record values, explicit schemas, explicit field/unit mappings,
schema-conformance validation, provenance, deterministic reports, and CPDataKit HDF5 1.0.

Crystal plasticity remains the first supported vertical. Its built-in `curve`, `point`, and
`field2d` contracts, DAMASK DADF5 adapter, stress/strain vocabulary, grain/phase summaries, and
specialized plots remain available and compatible. Structural validation continues to mean only
that the declared contract is satisfied; it does not certify physical correctness.

## 2. Repository state and baseline

The actual project is the nested Git repository at `cpdatakit/`. At audit time it was on
`main...origin/main` with 19 modified files and 10 untracked files. These include the in-progress
v0.4 release metadata, schema-diff implementation, comparison bundles, and their tests and design
documents. They are maintainer assets. The v0.5 implementation must layer changes onto the current
working tree, resolve overlapping edits surgically, and must not reset, check out, clean, delete, or
silently replace them.

Baseline commands were run from the nested repository with its existing `.venv` on 2026-09-01:

| Command | Exit | Actual result |
| --- | ---: | --- |
| `pytest` | 0 | 230 tests passed in 5.76 seconds |
| `ruff check .` | 0 | All checks passed |
| `ruff format --check .` | 1 | 1 file would be reformatted: `src/cpdatakit/_version.py`; 93 files already formatted |
| `python -m build` | 0 | Built `cpdatakit-0.4.0.tar.gz` and `cpdatakit-0.4.0-py3-none-any.whl` |

The `_version.py` formatting failure predates v0.5 and is not to be silently fixed during the design
phase. The implementation phase must report whether it remains a baseline issue or is resolved by an
authorized overlapping edit.

## 3. Current architecture audit

### 3.1 Already domain-independent

- `Dataset` is a pandas table plus open metadata and an optional source path. It contains no CP
  field names and deep-copies transformation state.
- `FieldSchema` and most of `ProfileSchema` already express general contracts: dtype, requiredness,
  fixed per-record shape, component order, role, unit, missing-value policy, aliases, ranges,
  indexes, uniqueness, descriptions, conventions, and an extension namespace.
- Schema parsing, deterministic serialization, canonical JSON, SHA-256 hashing, schema writing,
  description, and schema diff are general except for the profile-name whitelist.
- Validation is schema-driven. Dtype, shape, missing values, non-finite values, ranges, duplicates,
  indexes, unit compatibility, and undeclared fields do not depend on CP field names.
- Normalization is an explicit source-to-target mapping with Pint conversions. It already handles
  affine units and fixed-shape values without scientific inference.
- CSV, JSON-record, and most CPDataKit HDF5 read/write logic are domain-independent. HDF5 stores a
  profile identifier, schema version, units, mapping, provenance, validation summary, and an
  optional canonical schema snapshot.
- Inspection, sanitization, report rendering, provenance, aggregate comparison, overwrite
  protection, and CLI exit-code conventions are mostly generic.
- Histogram plotting and the mechanics of unit-labelled Matplotlib output are generic.

### 3.2 Crystal-plasticity assumptions still embedded

- `schema.py` defines `SUPPORTED_PROFILES = {"curve", "point", "field2d"}` and rejects every other
  profile even when loaded from an explicit JSON file.
- `io._read_hdf5_metadata()` independently rejects an HDF5 `profile` outside the same set. This
  blocks custom-profile round trips even if the file embeds a complete canonical schema.
- The built-in schemas contain CP vocabulary: stress, strain, grain, phase, orientation, tensor
  conventions, and material-point identifiers. `field2d` also carries optional grain/phase IDs.
- `statistics.summarize_dataset()` always emits `unique_grains` and `unique_phases`, including for
  profiles where those concepts do not apply. Fixed-shape numeric fields are not explicitly
  separated from scalar descriptive statistics.
- `plot_stress_strain()` and `plot_counts()` encode CP field names. The CLI plot choices have no
  schema-driven x-y operation, and the top-level CLI description says crystal-plasticity data.
- Inspection and reporting import and select `DamaskDADF5Adapter` directly. DAMASK format detection
  is hard-coded in HDF5 inspection, and adapter metadata has no shared descriptor/registry contract.
- Documentation and package metadata lead with crystal plasticity rather than the general contract
  boundary.

### 3.3 Compatibility risks

#### `Dataset`

- The stable object is intentionally tabular. A column may contain fixed-shape arrays, but there is
  no N-dimensional coordinate/index model. Replacing it with xarray or a new `DatasetV2` would
  break every validator, normalizer, reader, adapter, report, and caller.
- `metadata` is intentionally open and untyped. Existing producers depend on keys such as `units`,
  `profile`, `schema_version`, `field_mapping`, `adapter`, and `provenance`; making metadata a strict
  new dataclass in v0.5 would be incompatible.
- A `Dataset` does not own a schema. Callers can validate the same in-memory data against different
  contracts. v0.5 must not silently bind or infer a physical schema.

#### `ProfileSchema`

- The profile whitelist currently serves two different purposes: locating bundled schemas and
  deciding whether any schema is valid. Simply deleting the constant without separating those
  purposes can make built-in lookup ambiguous or weaken error messages.
- Current external-schema tests use custom fields but still name the profile `curve` or `point`, so
  the arbitrary-profile failure is largely untested.
- The existing `extension_prefix` behavior is a compatibility escape hatch used by DAMASK
  (`user_dadf5_...`). v0.5 must not broaden it into “accept any unknown field.” Arbitrary
  unprefixed fields remain errors, and the new generic example will declare every field, dtype,
  unit, and shape. Removing the existing prefixed-extension behavior would break DAMASK and is not
  part of v0.5.
- Canonical JSON serializes normalized defaults as well as supplied values. Adding required schema
  keys, changing defaults, normalizing profile names, or changing key/value representations would
  change existing hashes. v0.5 should add no required schema property and should preserve the
  current serialization algorithm byte-for-byte for existing contracts.
- Several public functions annotate narrower schema inputs than `validate_schema()` actually
  supports. The implementation should use one additive `SchemaInput` definition while retaining all
  existing accepted inputs.

#### CPDataKit HDF5 1.0

- The eight required root attributes and `format_version=1.0` are an established envelope. A new
  required root attribute or a version bump would make legacy files unreadable.
- Legacy HDF5 1.0 files may lack `schema_json` and `schema_sha256`; current tests guarantee that
  they remain readable for built-in profiles.
- Accepting any arbitrary root `profile` without a schema snapshot would weaken the contract: a
  reader could not establish what the name means. Conversely, continuing the whitelist prevents
  custom-profile files. The safe distinction is: legacy built-in profiles may omit a snapshot;
  non-built-in profiles must carry the already-defined canonical snapshot/hash pair.
- A custom schema snapshot must still match the root profile and schema version and pass canonical
  JSON and hash verification. `format_version` and supported `schema_version` remain `1.0`.

#### Adapter interface

- `DatasetAdapter.load(path)` is the only stable interface and existing third-party subclasses may
  implement only that method. Making new metadata or detection methods abstract would break them.
- DAMASK adapters require constructor selection options; a registry cannot assume every adapter is
  a zero-configuration universal reader.
- Format detection and successful loading are distinct. Detection may identify DADF5 while loading
  still requires an explicit label or dataset selection. The registry must not turn ambiguous
  scientific choices into implicit defaults.

## 4. Considered approaches

### Option A — Minimal whitelist removal only

Allow arbitrary profile strings in `ProfileSchema`, relax HDF5 profile checking, add `xy`, and
update copy. This is the smallest patch and keeps APIs stable.

Trade-off: it would accept custom HDF5 files without enough contract evidence, leave CP statistics
in every generic summary, and leave the adapter boundary hard-coded. It meets the happy path but
does not establish a durable scientific-data-core boundary.

### Option B — Progressive contract core with compatibility facades (recommended)

Separate “bundled profile lookup” from “valid external profile,” require embedded schemas for
non-built-in HDF5 profiles, make base statistics profile-neutral, preserve CP output only for the
three compatibility profiles, add a generic x-y plot, and add a small in-process adapter registry
with optional descriptors/detection. Keep `Dataset`, schema version 1.0, HDF5 format 1.0, import
paths, and existing named commands.

Trade-off: this touches several boundaries and requires a careful compatibility matrix, but each
change is additive or conditional. It provides the intended architecture without inventing schema
inheritance, a plugin platform, or a new storage model.

### Option C — New generic schema hierarchy and HDF5 2.0

Introduce base schemas plus CP schema inheritance, bind schemas to a new dataset type, move CP into
an optional package, and define a new storage envelope.

Trade-off: the separation is conceptually clean but creates migration machinery, hash changes,
package-boundary questions, and widespread API/format breaks. It also trends toward the universal
platform explicitly excluded from v0.5.

## 5. Recommended design

### 5.1 Layering

```text
CSV / JSON / CPDataKit HDF5        external scientific formats
              |                              |
        core readers                 registered adapters
              |                              |
              +-----------> Dataset <--------+
                                |
                     explicit mapping + schema
                                |
              validation / generic statistics / inspection
                                |
                  report / comparison / HDF5 1.0 / plots

CP vertical: built-in curve/point/field2d + DAMASK + CP statistics/plots
```

The generic core owns representation and declared conformance. A domain layer supplies contracts,
adapter selections, vocabulary, and specialized views. No layer infers physical semantics.

### 5.2 Schema and profile behavior

- Introduce `BUILTIN_PROFILES` for resource lookup and compatibility behavior. Keep
  `SUPPORTED_PROFILES` as a compatibility alias if tests or external callers import it.
- A `ProfileSchema.profile` from an explicit JSON file, JSON-like mapping, or object is valid when it
  is a non-empty string. It is preserved exactly; v0.5 will not slugify, case-fold, or infer it.
- Bare CLI/API names such as `curve` continue to resolve only bundled resources. A non-built-in
  profile is supplied through its JSON path or a `ProfileSchema`/mapping in the Python API. v0.5
  does not create a global schema catalog.
- Define and consistently use an additive `SchemaInput` union so schema-aware public functions keep
  accepting strings, paths, and `ProfileSchema`, while JSON-like mappings work where already
  documented.
- Keep supported dtypes, unit requirements, shapes, components, conventions, extension-prefix
  behavior, and schema version 1.0 unchanged.
- Preserve `schema_to_dict()`, compact sorted canonical JSON, UTF-8 hashing, and human-readable JSON
  behavior. Existing built-in schemas must produce the exact same canonical strings and SHA-256
  values before and after v0.5.
- Pin the audited built-in hashes in regression tests: `curve` is
  `6234e8cd78f0ad9f0251cd233fd7111f6c62fc17835289ab521369880977fa44`, `point` is
  `c668c4b05cf542ab4c3af8aba7b1b03ebd4a20d49186773b2a5a229f27e6c59b`, and `field2d` is
  `766d6ee0e1ad3b2a77d0fdffb3a5aec4274a33490a51315676fb48d57817e4b0`.
- Old schemas that omit optional keys continue to load through existing defaults. v0.5 adds no new
  required schema key.

### 5.3 HDF5 1.0 compatibility rule

The writer continues to write the current eight required root attributes plus the already-existing
`schema_json` and `schema_sha256` snapshot pair (and optional `schema_uri`). There is no
`format_version` bump.

Reader behavior becomes:

1. Require the existing eight attributes, `format=CPDataKit`, `format_version=1.0`, and
   `schema_version=1.0`.
2. Require `profile` to be non-empty text.
3. If a schema snapshot is present, validate its schema, exact canonical bytes, digest, root
   profile, and schema version exactly as today.
4. If the root profile is non-built-in, require that verified snapshot. Reject a custom profile
   without it with a clear `DataReadError`.
5. If the root profile is built-in, continue accepting legacy format-1.0 files without a snapshot.

This makes newly written custom-profile files self-describing while retaining every valid legacy
built-in file. Field selection, ranged reads, chunk iteration, atomic writes, shaped values, and
validation-summary behavior are unchanged.

### 5.4 Validation and normalization

- The validation engine remains field-schema-driven. It will not add checks for plausible stress,
  strain, temperature, grain counts, monotonic loading, constitutive behavior, or physical
  equivalence.
- Arbitrary undeclared fields continue to fail. The existing explicit `extension_prefix` namespace
  remains only for backward compatibility and adapter payloads; it is not expanded. The generic
  example uses fully declared fields.
- Mapping targets must remain declared in the schema. Unit conversions remain explicit and Pint
  checks dimensional compatibility only; it does not infer semantics.
- `Dataset` and `FieldMapping` remain structurally unchanged.

### 5.5 Statistics, inspection, reports, and comparison

- Base statistics include record/field counts, scalar numeric min/max/mean/std, missing/non-finite
  counts, validation status, and the existing scope note. Fixed-shape numeric fields are reported as
  unavailable for scalar descriptive statistics rather than flattened.
- Grain and phase counts move behind a CP-specific enrichment helper. For `curve`, `point`, and
  `field2d`, the existing `unique_grains` and `unique_phases` keys and values remain exactly
  compatible. Custom profiles do not receive irrelevant CP keys.
- Inspection and report rendering remain field-driven and display the actual profile string. They
  must work without grain, phase, stress, or strain fields.
- `build_report()` continues to require an explicit schema. It does not silently choose the HDF5
  snapshot as the analysis contract in v0.5.
- Report comparison continues to compare canonical schemas, declared structure, validation, and
  scalar aggregates. Once arbitrary profile validation is enabled, the current comparison engine
  works for same-profile custom reports; differing profile names remain a breaking schema diff.
- Scope notes continue to state that conformance and aggregate equality are not physical or
  scientific equivalence.

### 5.6 Plotting

Add a public helper with this behavior:

```python
def plot_xy(
    dataset: Dataset,
    schema: SchemaInput,
    x: str,
    y: str,
) -> tuple[Figure, Axes]:
    """Plot two declared scalar numeric fields with schema units."""
```

Both fields must be declared by the selected schema, present in the dataset, scalar, numeric, and
contain finite plottable values. Errors identify the missing/undeclared/non-scalar/non-numeric
field. Labels use schema units and output remains deterministic and headless-safe.

CLI syntax is additive:

```text
cpdatakit plot INPUT --schema SCHEMA --kind xy --x FIELD_X --y FIELD_Y --output result.png
```

`--x` and `--y` are required only for `xy`. Existing `stress-strain`, `histogram`, `grain-count`,
`phase-count`, and `field2d` choices, arguments, output protection, return codes, PNG/SVG behavior,
and Python import paths remain unchanged.

### 5.7 Adapter registration boundary

- Keep `DatasetAdapter.load(path)` abstract with the same signature. No new member required of old
  subclasses may be abstract.
- Add an immutable `AdapterInfo` value with `name`, `format_name`, and `capabilities`. Base-class
  defaults use the subclass name as identity/display text and `{"load"}` as capabilities, so an
  existing subclass that implements only `load()` remains concrete.
- Add an optional class-level detection hook whose default returns `False`. Detection answers only
  “this representation appears to be mine”; it does not choose scientific selections or guarantee
  that `load()` can proceed without configuration.
- Add an `AdapterRegistry` that registers an adapter class under a unique stable name, lists
  descriptors, resolves a name to its class, and returns every matching class for a path. Duplicate
  names fail clearly. A module-level default registry contains built-ins; tests and applications can
  create isolated registry instances. Resolution returns a class rather than constructing it, so
  callers still supply required scientific selection options explicitly.
- Register DAMASK DADF5 as the first built-in external adapter and give it header-based detection.
  Keep its selection logic, output `point` profile, `user_dadf5_` fields, units, provenance, and
  error behavior in `adapters/damask_dadf5.py`.
- Do not add Python entry-point discovery, remote plugins, solver runtime loading, or a large reader
  framework in v0.5. The registry is the stable seam for evaluating those later.
- Native CSV, JSON, and CPDataKit HDF5 readers remain core readers; they are not forced through the
  external-adapter registry in this release.

### 5.8 General scientific-data example

Add `examples/thermal-cycle/` as a non-CP, deterministic scalar time-series example:

```text
examples/thermal-cycle/
  README.md
  schema/thermal-cycle.json
  input/thermal-cycle.csv
  mappings/thermal-cycle.json
```

The profile is `thermal-cycle`. Its schema explicitly declares elapsed time, temperature, and cycle
stage, including dtypes, scalar shapes, units, requiredness, index/range rules, roles, and
descriptions. The raw CSV uses exporter-specific names and degrees Celsius/minutes; the mapping
renames fields and explicitly converts to Kelvin/seconds. No CP vocabulary is required.

The README demonstrates reproducible commands for `validate`, `summary`, `convert`, `inspect`,
`report`, `compare`, and `plot --kind xy`. Inspection and reporting operate on the converted HDF5,
which proves the custom profile and embedded schema pass the full storage path. Comparison can
compare two generated JSON reports without claiming physical equivalence. Tests use the checked-in
files directly and write outputs only to temporary directories.

## 6. Planned file impact

### Core implementation

- `src/cpdatakit/schema.py`: distinguish bundled names from valid external profile names; unify
  schema input typing without changing canonical output.
- `src/cpdatakit/io/__init__.py`: apply the conditional custom-profile snapshot rule while retaining
  HDF5 1.0 and legacy built-in reads.
- `src/cpdatakit/statistics.py`: make base scalar statistics generic and apply CP compatibility
  enrichment explicitly.
- `src/cpdatakit/plotting.py`: add `plot_xy`; retain existing plotting functions.
- `src/cpdatakit/cli.py`: generalize CLI description and add `xy`, `--x`, and `--y` dispatch.
- `src/cpdatakit/adapters/base.py`: add backward-compatible default descriptor/detection behavior.
- `src/cpdatakit/adapters/registry.py`: add the lightweight in-process registry.
- `src/cpdatakit/adapters/damask_dadf5.py`: declare DAMASK identity/capabilities and detection only;
  keep its load semantics.
- `src/cpdatakit/adapters/__init__.py`: expose the registry boundary without removing current exports.
- `src/cpdatakit/inspection.py` and `src/cpdatakit/reporting.py`: consume adapter detection/identity
  without moving DAMASK semantics into the core report model.
- `src/cpdatakit/__init__.py`: no new plotting re-export. `plot_xy` follows the established
  `cpdatakit.plotting` public-module style, and all current package-root exports remain.

`src/cpdatakit/model.py`, `validation.py`, and `normalization.py` are not expected to require
behavioral changes. Type-annotation-only alignment may be made if the tests demonstrate a need.

### Examples and tests

- Create the four `examples/thermal-cycle/` files above.
- Add focused tests for custom schemas and the generic example, likely
  `tests/test_scientific_data_core.py` and `tests/test_cli_scientific_example.py`.
- Extend `tests/test_schema.py`, `tests/test_io.py`, `tests/test_normalization_statistics.py`,
  `tests/test_plotting.py`, `tests/test_adapters.py`, `tests/test_damask_adapter.py`,
  `tests/test_inspection.py`, `tests/test_reporting.py`, `tests/test_comparison.py`, and relevant CLI
  tests only where their existing boundary is being changed.
- Update `.github/workflows/ci.yml` clean-wheel smoke coverage to exercise the custom schema and x-y
  path from installed artifacts. The publishing workflow is not changed before an actual release.

### Documentation and metadata

- `pyproject.toml`: description and keywords only; no package rename or release-version bump.
- `README.md` and `README.zh-CN.md`: general positioning first, CP as the first vertical, generic
  example, unchanged CP quickstart and compatibility statement.
- `docs/architecture.md`: document core/domain/adapter dependency direction.
- `docs/data-format.md`: document arbitrary external profiles and the conditional HDF5 snapshot rule.
- `docs/adapter-guide.md`: document descriptors, detection, registration, and ambiguity behavior.
- `docs/schema-authoring.md`: document custom profile names and fully declared generic contracts.
- `docs/roadmap.md`: record v0.5 scope and defer larger formats/models.
- `CHANGELOG.md`: add v0.5 work under `Unreleased` without disturbing the current uncommitted v0.4
  section.

## 7. TDD, compatibility, and migration strategy

Implementation is split into reviewable red-green-refactor slices. Every slice starts with a
focused failing test, applies the smallest production change, and reruns the focused test plus the
relevant existing module tests before moving on.

1. **Profile acceptance:** prove a JSON `thermal-cycle` schema loads, validates declared data,
   rejects undeclared fields, and preserves built-in profile behavior.
2. **Canonical stability:** capture current canonical JSON and exact hashes for all three built-ins,
   then prove they do not change; prove reordered source JSON for a custom profile canonicalizes to
   the same bytes/hash.
3. **HDF5 compatibility:** prove a custom-profile round trip, custom profile without snapshot
   rejection, custom root/snapshot mismatch rejection, existing writer round trips, and hand-built
   legacy built-in HDF5 without the additive snapshot.
4. **Generic analysis surfaces:** prove summary, inspect, report, and report comparison work without
   CP fields; prove existing built-ins retain `unique_grains`/`unique_phases` output.
5. **Generic x-y plotting:** prove API and CLI output, declared-field/type/shape errors, output
   protection, exit status 0/1/2 behavior, and no regression in all existing plot kinds.
6. **Adapter boundary:** prove old subclasses implementing only `load()` still instantiate, registry
   identity and duplicate behavior are deterministic, DAMASK detection works, ambiguous DADF5 loads
   remain explicit, and all DAMASK tests pass.
7. **Example E2E:** run the checked-in thermal-cycle inputs through validate, summary, convert,
   inspect, report, compare, and x-y plot in a temporary directory and verify HDF5 profile/schema
   snapshot metadata.
8. **Documentation and distribution:** update copy after behavior is green, build distributions,
   install the wheel into a clean environment outside the source tree, and execute both the existing
   CP quickstart smoke and the custom-profile smoke.

Compatibility is guarded by the following matrix:

| Surface | v0.5 rule |
| --- | --- |
| `Dataset` | No structural change |
| `DatasetAdapter.load()` | Same abstract signature; new methods are optional/defaulted |
| Built-in profile APIs | `curve`, `point`, `field2d` names and behavior retained |
| CLI | Existing commands/options/exit codes retained; `xy`, `--x`, `--y` are additive |
| HDF5 | `format_version=1.0`; existing eight required attrs unchanged |
| Legacy HDF5 | Built-in profiles without schema snapshots remain readable |
| Current HDF5 | Canonical snapshot and digest checks remain strict |
| Schema hashes | Existing canonical bytes and hashes unchanged |
| DAMASK | Adapter load/inspection/report examples and tests remain green |
| Validation meaning | Declared structural conformance only |

No automatic migration is required because the data model, schema version, and HDF5 envelope do not
change. Custom HDF5 producers must use the current writer or supply the existing canonical
snapshot/hash pair. Any future schema-version migration remains explicit and follows the existing
schema-diff design.

At completion, run and report the real output from:

```text
pytest
pytest --cov=cpdatakit
ruff check .
ruff format --check .
python -m build
clean wheel smoke test
```

The final implementation report must distinguish a newly introduced failure from the recorded
baseline formatting failure; it may not say “should pass” or “expected to pass.”

## 8. Explicit non-goals for v0.5

- xarray or a complete N-dimensional array data model.
- Unstructured meshes, mesh topology, graph data, or spatial interpolation.
- NetCDF, Zarr, Parquet, or a broad set of new storage formats.
- GUI, web platform, cloud catalog, database, account, or collaboration service.
- Automatic field, unit, role, coordinate, tensor, orientation, or physical-semantic inference.
- Physical correctness, physical equivalence, constitutive-law checks, or scientific interpretation.
- AI analysis or automatic scientific explanation.
- Full Abaqus ODB runtime integration.
- Solver execution or result generation.
- Dynamic package/plugin discovery, remote adapter installation, or a general solver-adapter suite.
- HDF5 2.0, schema inheritance/composition, package rename, PyPI rename, or removal of the
  `cpdatakit` import path.
- A release version bump, commit, push, tag, or pull request as part of this task unless separately
  authorized.

If any implementation slice appears to require one of these items, implementation stops and the
maintainer receives the concrete reason and alternatives before scope changes.
