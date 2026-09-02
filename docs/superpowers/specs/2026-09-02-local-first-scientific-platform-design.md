# CPDataKit Local-First Scientific Platform Design

**Date:** 2026-09-02
**Status:** Written after approval of the v0.6-v0.9 expansion roadmap; implementation remains gated
on maintainer review of this document.

## 1. Outcome

CPDataKit will grow from a schema-first validation toolkit into a local-first scientific data
workbench. A normal installation provides four interfaces over the same application services:

- `cpdatakit ui` opens the default browser and serves a local web application.
- Existing CLI commands remain suitable for scripts and CI.
- The Python API remains the integration surface for notebooks and libraries.
- A later self-hosted server mode reuses the same services for teams.

The default product works offline and does not require an account, commercial model, cloud service,
or proprietary solver. Integrations that legally or technically require an external runtime report
their availability and setup requirements without disabling the rest of the application.

## 2. Delivery structure

This program is split into four independently usable releases. Each release receives its own
implementation plan, TDD cycle, compatibility audit, clean-package smoke test, and project-facing
documentation pass.

| Release | User-visible result | Primary architecture change |
| --- | --- | --- |
| v0.6 | Local web workbench plus N-dimensional/open-format support | Shared application service layer, xarray-backed data, schema/HDF5 2.0 |
| v0.7 | Structured and unstructured spatial data | Mesh/topology contract and spatial visualization |
| v0.8 | Explicit domain checks, inference proposals, and optional AI providers | Separate structural, domain, inference, and explanation result types |
| v0.9 | Solver jobs, Abaqus bridge, local catalog sharing, and self-hosted collaboration | Job runtime, integration bridge, server/auth boundary |

Later releases build on the previous version. They do not reopen completed compatibility contracts
without a schema diff and migration design.

## 3. Cross-version constraints

### 3.1 Compatibility

- Keep the package name and `cpdatakit` import path.
- Keep the current tabular `Dataset`, `curve`, `point`, `field2d`, thermal-cycle profile, CLI
  commands, DAMASK adapter, and CPDataKit HDF5 1.0 reader.
- Existing HDF5 1.0 files remain readable. Writers use 1.0 for lossless tabular data unless a caller
  selects a feature that requires HDF5 2.0.
- No operation silently flattens N-dimensional arrays, changes units, rewrites tensor order,
  converts physical measures, or applies inferred semantics.
- New result types are additive. `ValidationResult.valid` continues to describe the declared
  structural contract only.

### 3.2 Offline and distribution behavior

- v0.6 requires Python 3.12 or later. CPDataKit 0.5.x remains the supported line for Python 3.10
  and 3.11 users. The version-floor change is announced in release notes, installation docs, and
  package metadata before the first v0.6 pre-release.
- `pip install cpdatakit` includes the local UI and open-source format support needed by v0.6.
- Runtime assets are bundled in the wheel. The UI uses no CDN, remote font, analytics endpoint, or
  mandatory network request.
- `cpdatakit ui` binds to loopback only, chooses an available port, opens the browser, and prints the
  URL. A no-browser flag supports remote terminals and CI.
- Abaqus, commercial solvers, cloud AI services, and GPU runtimes are optional integrations. Their
  absence appears as an unavailable capability with a concrete diagnostic.
- Windows, macOS, and Linux are supported for the core, UI, and open formats. An integration may
  declare a narrower platform matrix when its upstream runtime does.

### 3.3 Safety

- Local UI requests carry a random session token and CSRF protection. Host checks reject non-local
  origins by default.
- Uploaded files enter a per-project workspace. File names are normalized, archive traversal is
  rejected, and output replacement still requires an explicit force action.
- Format probing uses bounded reads. Preview and inspection paths do not materialize entire large
  datasets without a visible user choice.
- Solver processes never use `shell=True`. Commands are argument arrays, working directories are
  explicit, environment inheritance is filtered, and cancellation terminates the owned process
  tree.
- The project does not ship proprietary libraries, credentials, solver binaries, or third-party
  model weights without redistribution rights.

## 4. Shared application architecture

```text
Browser UI       CLI       Python API       Team API (v0.9)
     \            |            |                 /
            application services
     import / contracts / validation / jobs / reports / catalog
                    |
       readers and adapters registry
                    |
 Tabular Dataset | ScientificDataset | MeshDataset
                    |
 CSV JSON HDF5 NetCDF Zarr Parquet mesh/solver integrations
```

The UI, CLI, and Python API call application services rather than each reimplementing workflow
logic. Services accept typed request values and return existing or additive domain results. Web
routes contain HTTP concerns only. CLI handlers remain thin argument adapters.

Suggested package boundaries are:

```text
src/cpdatakit/
  application/       use cases shared by UI, CLI, and Python callers
  catalog/           local SQLite records and project workspaces
  data/              tabular, N-dimensional, and later mesh values
  formats/           native reader/writer registrations
  schemas/           schema models, resolution, canonicalization, migration
  web/               FastAPI routes, server-rendered views, bundled assets
  jobs/              background work and later solver processes
  domains/           CP and other explicit scientific checks
  adapters/          external representation integrations
```

Existing modules remain importable. They may delegate into these packages after characterization
tests protect their behavior.

## 5. v0.6 detailed design

The v0.6 dependency baseline follows the current N-dimensional stack rather than pinning legacy
xarray or Zarr releases to preserve Python 3.10. Candidate lower bounds are proven in a dedicated
preflight matrix before they enter `pyproject.toml`. The default install uses explicit FastAPI,
Uvicorn, Jinja, and multipart dependencies instead of `fastapi[standard]`, which would also install
cloud-oriented tooling outside the local-first runtime boundary.

### 5.1 Installation and local web UI

The web application uses FastAPI, Uvicorn, Jinja templates, and small bundled JavaScript modules.
Server-rendered HTML is the baseline. The wheel does not require Node.js at runtime and does not load
assets from the network.

Initial screens are:

1. Project home with recent local projects and a new-project action.
2. Import screen with format detection, bounded preview, and reader choice when detection is
   ambiguous.
3. Contract screen for built-in, uploaded, or composed schemas and explicit mappings.
4. Validation screen with errors, warnings, fields, units, shapes, and downloadable JSON.
5. Explore screen with table/N-dimensional summaries and schema-driven plots.
6. Convert screen with target capability checks and overwrite confirmation.
7. Report/compare screen with existing offline artifacts and side-by-side comparisons.
8. Capability screen listing available readers, adapters, solvers, and optional providers.

Long imports, conversions, and reports run through an in-process job manager. The UI polls a job
resource and can cancel work. v0.6 does not claim crash-resistant distributed execution. Each job
records start/end time, status, operation log, input/output basenames, and sanitized errors.

### 5.2 Local catalog

SQLite stores project, dataset, schema, artifact, and job records. Dataset bytes remain files in a
project workspace. The database stores relative paths, hashes, metadata, and relationships.

The catalog is optional to Python and CLI callers. Existing direct-path workflows keep working.
Schema migrations use numbered transactions and create a backup before changing a non-empty local
catalog. Removing a catalog entry never deletes source data unless the user selects a separate,
explicit file-removal action.

### 5.3 N-dimensional data model

Add `ScientificDataset`, an xarray-backed value with explicit metadata and an optional source:

```python
@dataclass(slots=True)
class ScientificDataset:
    data: xarray.Dataset
    metadata: dict[str, Any]
    source: Path | None = None

    def copy(self) -> ScientificDataset: ...
```

Dimensions, coordinates, data variables, attributes, units, and fixed component labels remain
explicit. `Dataset` remains the tabular type. Conversion functions have closed conditions:

- `dataset_to_scientific()` maps the record axis and fixed trailing shapes losslessly.
- `scientific_to_dataset()` succeeds only when one record dimension and fixed per-record variables
  can reproduce the tabular contract.
- A failed lossless conversion raises a structured error and never flattens data automatically.

### 5.4 Schema 2.0 and composition

Schema 1.0 remains unchanged. Schema 2.0 adds declarations for dimensions, coordinates, variables,
attributes, chunk hints, and optional topology references reserved for v0.7.

Composition uses two explicit mechanisms:

- `extends` names one base schema whose declarations are inherited.
- `includes` names reusable fragments that add declarations without an inheritance hierarchy.

Resolution is local by default. Sources may be package resources, filesystem paths, or registry
identifiers already installed in the process. HTTP fetching is disabled unless a caller supplies a
resolver. Cycles, duplicate declarations, incompatible overrides, version mismatches, and ambiguous
relative paths fail before data is read.

Canonical JSON for schema 2.0 is computed over the fully resolved contract plus a source manifest.
The manifest records every source URI/path label and hash. Changing a fragment changes the resolved
hash. Schema 1.0 canonical bytes and the three pinned built-in hashes remain unchanged.

### 5.5 HDF5 2.0

HDF5 2.0 stores N-dimensional variables without pretending they are one table:

```text
/
  attrs: format, format_version=2.0, schema_version, schema_json, schema_sha256, ...
  /dimensions
  /coordinates
  /variables
  /metadata
```

Each variable records its ordered dimension names, unit, dtype, chunks, compression, and declared
role. Coordinates are first-class datasets. Provenance, mapping, validation summary, schema snapshot,
atomic replacement, and hash verification carry forward from 1.0.

The reader dispatches by root `format_version`. The v1 reader is retained rather than rewritten as
a v2 special case. A v1-to-v2 conversion is explicit and covered by a migration manifest. A v2 file
is written only for `ScientificDataset` or a caller's explicit v2 request.

### 5.6 Format capability matrix

| Format | Read | Write | Data model | Boundary |
| --- | --- | --- | --- | --- |
| CSV | yes | existing behavior | `Dataset` | scalar columns |
| JSON records | yes | existing behavior | `Dataset` | record objects |
| HDF5 1.0 | yes | yes | `Dataset` | existing contract |
| HDF5 2.0 | yes | yes | `ScientificDataset` | N-dimensional contract |
| NetCDF | yes | yes | `ScientificDataset` | xarray-compatible groups/variables |
| Zarr | yes | yes | `ScientificDataset` | local stores first; remote stores require explicit filesystem configuration |
| Parquet | yes | yes | `Dataset` | tabular fields; nested fixed-shape values only when Arrow schema is lossless |

Writers expose capability checks before creating output. Parquet does not accept arbitrary
N-dimensional data. NetCDF encoding limitations return errors naming the unsupported dtype,
attribute, or variable.

### 5.7 Registry and plugins

The existing `AdapterRegistry` grows into typed registries for readers, writers, plots, domain
checks, solvers, and explanation providers. Python entry points provide discovery. Discovery reads
metadata without importing every plugin. Enabling a plugin imports it in-process and validates its
declared API version and capabilities.

Plugins cannot silently replace a built-in registration. Name collisions and incompatible API
versions are visible errors. A safe-mode flag disables third-party plugins. The capability screen
shows package name, version, declared formats, availability, and any failed dependency check.

### 5.8 v0.6 acceptance

- A new environment can install the wheel and run `cpdatakit ui` without network access after
  installation.
- The browser completes the existing thermal-cycle and CP curve workflows without using a terminal.
- CLI and Python behavior from v0.5 remains green.
- One checked-in N-dimensional example completes schema validation and HDF5 2.0, NetCDF, and Zarr
  round trips. A tabular example completes Parquet round trip.
- Schema composition has deterministic resolved JSON/hash tests, cycle/conflict failures, and a
  migration-safe source manifest.
- Large-file previews use bounded reads and expose when an operation will materialize data.
- UI tests cover route behavior, CSRF/session checks, file boundaries, output protection, job
  cancellation, and accessibility of the main workflow.
- Source and wheel verification run on Python 3.12 and 3.13 across Windows and Linux. macOS receives
  clean-wheel install, format import, and UI startup smoke coverage. A newer Python version joins
  the matrix only after xarray, Zarr, Arrow, NetCDF, and UI dependencies all publish compatible
  wheels.

## 6. v0.7 spatial and mesh design boundary

Add `MeshDataset` with coordinates, typed cell blocks, connectivity, point/cell/global fields, and
explicit coordinate reference metadata. Connectivity is integer and bounds-checked. Mixed cell
types remain separate blocks. Topology is never inferred from spatial proximity.

The schema declares topology roles, entity association, coordinate dimensions, index bases, and
field locations. Structural checks cover connectivity shape/range, orphaned references, field/entity
count agreement, and declared coordinate systems. Interpolation, element quality, and physical
meaning are separate operations with named methods and reports.

The first open interchange path uses a well-supported mesh library behind the format registry.
Checked-in redistribution-safe fixtures cover at least one structured grid and one mixed-cell
unstructured mesh. The UI adds bounded 2D/3D previews with bundled assets and an explicit downsample
indicator.

## 7. v0.8 domain checks, inference, and explanation

Four outputs remain distinct:

```text
ValidationResult          declared structure passed or failed
DomainCheckResult         named scientific rule and evidence
InferenceProposal         proposed schema/mapping plus confidence and evidence
ExplanationArtifact       narrative generated from cited results
```

Domain checks are opt-in plugins. Each declares supported profiles, required fields, assumptions,
algorithm version, parameters, and evidence. A failed domain check never changes structural
validation status.

Inference only proposes changes. The user reviews and accepts a generated schema or mapping before
normalization/conversion. Every proposal records candidates considered, confidence, evidence, and
unresolved ambiguity. Unit compatibility can rank candidates. It cannot establish physical
equivalence by itself.

Deterministic explanation templates work offline. AI providers are optional plugins with local and
remote implementations. Provider calls receive sanitized aggregate artifacts by default, never raw
records or credentials. Sending raw data requires a separate explicit action and a visible provider
destination. Generated claims cite the validation/domain/statistics artifact entries they use.

## 8. v0.9 solver and collaboration design boundary

### 8.1 Solver jobs

`SolverSpec` declares executable discovery, argument templates, required inputs, outputs, supported
platforms, environment allowlist, timeout behavior, and result adapter. `SolverJob` records the
resolved executable, arguments, working directory, timestamps, exit code, captured logs, output
hashes, and cancellation state.

The generic runner executes local processes only in the first release. It does not interpret solver
science. Docker or scheduler backends implement the same job interface later. The UI shows the exact
command and workspace before execution and requires confirmation.

### 8.2 Abaqus ODB

The open-source wheel ships a bridge protocol and extractor script, not Abaqus libraries. Runtime
detection locates supported Abaqus Python commands and reports their versions. The main process sends
an explicit extraction request to the Abaqus-owned interpreter and reads a neutral manifest/result.

The adapter requires an installed, licensed Abaqus environment. Without it, every other CPDataKit
feature remains usable and the capability screen gives the failed discovery evidence. Tests use an
open synthetic bridge fixture and contract tests; real-runtime certification runs only in a legally
provisioned environment.

### 8.3 Collaboration

Local project export creates a deterministic bundle with manifests and member hashes. Import checks
every member before registering it in the local catalog.

Self-hosted mode adds PostgreSQL-compatible catalog storage, object storage, accounts, project roles,
audit events, and background workers. A Docker Compose reference deployment is provided. Local mode
does not require this service. Authentication and authorization are server concerns and do not leak
into core data objects.

## 9. Testing and migration program

Every release uses TDD. Compatibility fixtures are append-only and include:

- Built-in schema hashes and HDF5 1.0 legacy files.
- Current CP, DAMASK, Surfalex, and thermal-cycle workflows.
- N-dimensional, Parquet, NetCDF, Zarr, structured-grid, and unstructured-mesh examples as their
  versions land.
- Plugin collision, missing dependency, and safe-mode cases.
- Solver bridge success, timeout, cancellation, malformed manifest, and unavailable runtime cases.
- Local bundle tamper cases and self-hosted authorization tests.

Migration commands are explicit, produce a manifest, preserve the source by default, and write
atomically. A migration result records source/target schema hashes, source/target format versions,
operations, warnings, provenance, and output hash.

Release verification includes `pytest`, coverage at or above the current 85% CI gate, Ruff checks,
reproducible build checks, distribution inspection, and clean-wheel smoke tests. UI and service tests
must run without external network access.

## 10. Documentation and humanization pass

After each release behavior and command set are stable, review all project-facing prose touched by
that release:

- README and README.zh-CN.
- Architecture, format, adapter, schema, quickstart, roadmap, and deployment guides.
- Example READMEs, CLI help/error messages, UI labels, empty states, report templates, and release
  notes.

The edit preserves API names, commands, paths, versions, numbers, citations, scientific claims, and
scope warnings. It removes repetitive scaffolding, uniform sentence rhythm, promotional language,
and generic assistant-style transitions. Technical docs stay direct and maintainer-like. No rewrite
claims to evade disclosure or guarantees a detector score.

Automated literal scans flag excessive em dashes, curly quotes, banned filler phrases, and repeated
openers in prose files. Maintainer review checks factual drift after rewriting. Code, fixtures,
canonical JSON, generated manifests, and test expectations are excluded unless they contain a
user-facing sentence whose wording is intentionally part of the product.

## 11. Program non-goals

- Bundling proprietary solver runtimes or bypassing their licenses.
- Making physical claims without a named check, assumptions, evidence, and versioned method.
- Automatically applying inferred schema, unit, tensor, orientation, or semantic changes.
- Sending user data to a remote AI or cloud service without an explicit destination and action.
- Requiring team infrastructure for local use.
- Replacing `cpdatakit` package/import names during v0.6-v0.9.
- Treating one release as a single all-or-nothing rewrite.
