# v0.6 local UI security and operation boundary

The default UI is a local tool. It binds to loopback, opens a browser, and keeps project data on the
local filesystem. The server has no cloud account, no telemetry, and no outbound requests in its
normal workflow.

The first implemented vertical slice is available through `cpdatakit.web.create_app(workspace)`:
health and home pages, local project creation, and bounded upload-to-inspect flow. It uses the
application service result envelope and stores uploaded sources under the selected workspace.

## Network and session boundary

The host validation rule, path containment rule, and job cancellation rule are explicit contracts for
the implementation and its tests.

- Bind only to `127.0.0.1` by default. A caller must explicitly opt into another interface.
- Check the `Host` header against the bound host and configured port. Reject unexpected hosts.
- Create a random session token when the UI starts. Store it in a SameSite, HttpOnly cookie and
  require it on state-changing requests.
- Add a per-session CSRF token to forms and verify it for every state-changing route.
- Do not load scripts, fonts, CSS, analytics, or API data from a CDN or remote endpoint.

## Workspace and file boundary

Path containment is checked after resolving every path.

- Give each project a dedicated workspace. Resolve every path and verify it stays under that workspace
  before reading or writing.
- Normalize uploaded file names and reject empty names, symbolic-link escapes, and archive traversal
  entries such as `../secret`.
- Enforce an upload size and a bounded preview size before parsing. Large-file operations state when
  they will materialize records or arrays.
- Write artifacts through the existing atomic replacement path. Existing outputs require an explicit
  overwrite confirmation and force flag.
- Store source bytes by reference or copy according to the project setting. Catalog removal does not
  remove source files unless the user selects a separate file-removal action.

## Jobs and cancellation

Job cancellation is cooperative and must leave the workspace in a readable state.

The in-process job manager records an operation ID, start/end times, status, input/output basenames,
and sanitized errors. Job cancellation reaches the owning reader or writer and leaves no partial
artifact. Solver processes are outside v0.6, so the UI does not execute arbitrary commands yet.

## SQLite catalog

SQLite stores project, dataset, schema, artifact, and job metadata. It stores relative paths and
hashes rather than credentials or raw secrets. Schema migrations run in numbered transactions and
make a backup before changing a non-empty catalog. Database corruption is reported as a catalog
error and never silently recreated over the old file.

## Logging and failure responses

Logs include operation IDs and safe basenames. They redact credentials, tokens, absolute paths, and
raw records. HTTP errors expose a stable code and user action. Unexpected exceptions receive a
correlation ID while the browser sees a generic failure page.

## Explicit network policy

The default local workflow makes no outbound requests. Remote stores, cloud catalogs, AI providers,
and team accounts are separate capabilities that are disabled until the user configures and confirms
them. Capability discovery reports them as unavailable rather than attempting a connection.
