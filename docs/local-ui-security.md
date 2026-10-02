# Local UI security and operation boundary

The default UI is a local tool. It binds to loopback, opens a browser, and keeps project data on the
local filesystem. The server has no cloud account, no telemetry, and no outbound requests in its
normal workflow.

The first implemented vertical slice is available through `cpdatakit.web.create_app(workspace)`:
health and home pages, local project creation, and bounded upload-to-inspect flow. It uses the
application service result envelope and stores uploaded sources under the selected workspace.

## Network and session boundary

The host validation rule, path containment rule, and job cancellation rule are explicit contracts for
the implementation and its tests.

- The CLI binds to loopback only (`127.0.0.1`, `localhost` or `::1`), defaulting to `127.0.0.1`.
- Check the hostname in the `Host` header against the bound host. The comparison uses the hostname
  after parsing the optional port. Reject unexpected hosts.
- Create a random session token when the UI starts. Store it in a SameSite, HttpOnly cookie and
  require it on state-changing requests. Cookie names are scoped by an opaque workspace digest;
  separate local ports/workspaces can share a browser without overwriting each other's session.
- Add a per-session CSRF token to forms and verify it for every state-changing route.
- Serve bundled scripts, fonts, and CSS locally.

## Workspace and file boundary

Path containment is checked after resolving every path.

- Give each project a dedicated workspace. Resolve every path and verify it stays under that workspace
  before reading or writing.
- Normalize uploaded file names and reject empty names, symbolic-link escapes, and archive traversal
  entries such as `../secret`.
- Validate the session and any supplied header CSRF token before reading an upload body. A
  form-only token is checked after bounded multipart parsing. Enforce the configured upload size
  limit and file payload budgets before
  queuing spool writes, including aggregate Zarr uploads (at most 1000 files). Schema uploads use
  the smaller of the configured upload budget and 1 MiB; other file routes accept one file.
- Bound multipart requests to their file budget plus 3 MiB + 64 KiB of framing/form overhead;
  allow at most 64 fields, 2 MiB + 64 KiB aggregate field bytes and 8 KiB per-part headers. Count
  actual bytes even without a trustworthy Content-Length, and feed the parser at most 16 KiB at a
  time. A transport may already have delivered one larger ASGI frame; it is not spooled in full.
- Close all owned spool files on parse failure, disconnect, cancellation, rejection and completion.
  Record and materialization limits also apply to bounded data reads. Simple variable-length HDF5
  strings use conservative file-size/count estimates; numeric, nested and compound variable-length
  payloads whose allocation cannot be estimated safely are rejected by bounded readers.
- Write artifacts through the existing atomic replacement path. Existing outputs require an explicit
  overwrite confirmation and force flag.
- Keep registered versions under the reserved `.artifacts` directory. Registration verifies the
  produced digest; changed download content is rejected. Recovery never replaces a detected
  concurrent output and retains the old backup with a recovery manifest.
- Store source bytes by reference or copy according to the project setting. Catalog removal
  preserves source files; a separate file-removal action handles source deletion.

Single-file and Zarr uploads bind catalog registration to the identity and content digest captured
from their private staging output. Registration checks the public target before and after the
catalog write. Failed uploads remove only a matching item: rollback first moves it into a random
private quarantine, then checks identity and content again. A replacement or modification in that
interval is retained in quarantine with a workspace-relative recovery record. A newly occupied
public name is preserved. Inspect the response's `recovery` locations before retrying; restore a
retained item only to an unused destination. If writing a recovery record itself fails, the response
sets `record_written` to false and supplies the available locations.

The operation owns its random staging and quarantine directories. Failed cleanup of private
staging after successful registration is logged, and the completed upload retains its result.

## HDF5 container dependencies

Filesystem containment is not sufficient for HDF5: links, raw external storage and virtual
datasets can obtain values from other files while the uploaded container's hash stays unchanged.
HDF5 inspection and readers therefore require a self-contained container before loading payloads.
ExternalLink, external raw storage, VDS and SoftLink are rejected, including unused branches and
dangling links. Internal HardLinks are supported with cycle detection. The policy also covers
CPDataKit HDF5 2.0, DAMASK and HDF5-backed NetCDF; classic NetCDF3 is not affected.

The default policy has no trusted-path bypass. An error reports the unsupported dependency
category without reading or echoing an external target. Users who need data from an external
dependency must explicitly produce a separate self-contained file with a trusted producer;
the workbench never discovers, follows or copies arbitrary dependency paths on their behalf.

## Jobs and cancellation

Job cancellation is cooperative and must leave the workspace in a readable state.

The in-process job manager records an operation ID, start/end times, status, input/output basenames,
and sanitized errors. Job cancellation reaches the owning reader or writer and preserves complete
artifacts. A failure during cancellation retains CANCELLED status, an error summary, and a local log;
a normal checkpoint cancellation has an empty error field.

The workbench admits a job only after its catalog row exists. Failed admission cancels the worker
and releases its gate. Completed results are persisted before memory retirement. Default limits
are 64 pending jobs, 256 retained completed jobs, and 256 progress entries of 512 characters.
Historical details remain in the catalog and are loaded on demand.

Project pages and the project API include a separate, bounded `active_jobs` summary for workers
owned by this app instance. History retains its existing pagination and counts; rows are deduplicated
by ID in the browser. A persisted `running` row from a previous instance offers details rather than
live cancellation or automatic polling. Unpaginated API clients still receive the complete history
and result payloads.

## SQLite catalog

SQLite stores project, dataset, schema, artifact, and job metadata. It stores relative paths and
hashes rather than credentials or raw secrets. Schema migrations run in numbered transactions and
make a backup before changing a non-empty catalog. Database corruption is reported as a catalog
error and never silently recreated over the old file.

Catalog schema v4 adds job result JSON and project indexes. Migration uses SQLite's backup API
and a transaction so committed WAL data is included in the backup and failed DDL is rolled back.

## Logging and failure responses

Service responses sanitize input paths and expose a stable code and user action. Local recovery
diagnostics identify retained staging or backup paths so operators can inspect them. Unexpected
exceptions receive a correlation ID while the browser sees a generic failure message.

## Explicit network policy

The default local workflow makes no outbound requests. Remote stores, cloud catalogs, AI providers,
and team accounts are separate capabilities that are disabled until the user configures and confirms
them. Capability discovery reports them as unavailable rather than attempting a connection.
