# Comparison and Report Bundle Implementation Plan

> For agentic workers: use the repository's approved subagent or executing-plan workflow to implement this plan task-by-task. Steps use checkbox syntax for tracking.

Goal: Add deterministic aggregate comparison and bundle artifacts for two existing CPDataKit JSON reports without loading or exposing raw records.

Architecture: Keep reporting.py as the single report renderer source. Add a pure comparison module that consumes sanitized report mappings, delegates schema classification to diff_schemas(), and writes one canonical comparison mapping into JSON, Markdown, HTML, and a hashed manifest. Add CLI orchestration only after the pure API is tested.

Tech Stack: Python 3.10+, JSON, pathlib, hashlib, existing inspection/reporting helpers, pytest, Hypothesis, Ruff, and Hatchling.

Spec: docs/superpowers/specs/2026-08-31-comparison-report-bundles-design.md

## Global Constraints

- The first slice consumes existing JSON report payloads; it does not compare raw records or claim physical equivalence.
- Reuse render_report_json(), render_report_markdown(), render_report_html(), sanitization, and diff_schemas().
- Compare only scalar numeric statistics already present in reports; shaped/unavailable values remain explicitly unavailable.
- Keep validation errors/warnings side by side and preserve deterministic field/order semantics.
- Bundle members contain no raw records, absolute paths, secrets, JavaScript, external resources, or network calls.
- Existing output directories remain protected unless force=True; failed bundle writes clean partial members.
- Keep all existing report APIs and CPDataKit HDF5 format-1.0 behavior compatible.

---

### Task 1: Specify comparison behavior with failing tests

Files:
- Create: tests/test_comparison.py

Interfaces:
- Produces expected behavior for compare_reports(left, right) -> dict[str, Any] and
  write_comparison_bundle(comparison, output, force=False) -> Path.

- [ ] Step 1: Add identical-report tests

  Build two equivalent report mappings and assert identical schema classification, empty structural
  changes, no statistic deltas, stable scope note, and JSON-safe output.

- [ ] Step 2: Add structure and statistic comparison tests

  Add fields on one side, remove fields on the other, change schema properties, vary record counts,
  and change finite scalar statistics. Assert exact fields_added, fields_removed, fields_changed,
  and statistics.changed entries with left, right, and delta.

- [ ] Step 3: Add unavailable/shaped/safety tests

  Pass shaped statistics and not available values and assert they appear under unavailable without
  flattening. Include absolute paths, credential-like values, and HTML-looking strings; assert
  sanitized comparison output contains none of them.

- [ ] Step 4: Add bundle member/manifest tests

  Assert exactly manifest.json, comparison.json, comparison.md, and comparison.html are created;
  every member has a deterministic SHA-256 in the manifest; HTML is escaped and contains no script
  or external resource; repeated writes from the same mapping produce identical bytes.

- [ ] Step 5: Run the focused tests before implementation

  Run: pytest tests/test_comparison.py -q
  Expected: import failure because the comparison module and functions do not exist yet.

### Task 2: Implement pure aggregate comparison

Files:
- Create: src/cpdatakit/comparison.py
- Modify: src/cpdatakit/__init__.py
- Test: tests/test_comparison.py

Interfaces:
- Produces compare_reports(left, right) -> dict[str, Any].

- [ ] Step 1: Sanitize and normalize report inputs

  Pass both mappings through sanitize_for_output(), validate that the required report sections are
  mappings, and preserve safe basenames, schema hashes, record counts, validation mappings, and
  aggregate statistics only.

- [ ] Step 2: Delegate schema comparison

  Read the embedded schema definitions from both reports and call diff_schemas(). If one report
  lacks a schema definition, return an explicit unavailable comparison entry rather than guessing.

- [ ] Step 3: Compare fields and scalar statistics in fixed order

  Compare report field names in left/right order. For statistics.numeric_fields, compare only finite
  scalar min, max, mean, and std; emit unavailable entries for shaped or missing values. Never
  include source record values.

- [ ] Step 4: Export the pure API

  Add compare_reports to the package root and __all__. Keep no filesystem or network side effects in
  the pure function.

- [ ] Step 5: Run comparison and report regressions

  Run: pytest tests/test_comparison.py tests/test_reporting.py tests/test_inspection.py -q
  Confirm existing report payloads and renderers are unchanged.

### Task 3: Implement deterministic bundle writing

Files:
- Modify: src/cpdatakit/comparison.py
- Test: tests/test_comparison.py

Interfaces:
- Produces write_comparison_bundle(comparison, output, force=False) -> Path.

- [ ] Step 1: Render all members from one canonical mapping

  Use sorted-key JSON with one final newline, fixed Markdown sections, and the existing escaped
  static HTML renderer. Ensure all member content is sanitized before hashing.

- [ ] Step 2: Write through a same-parent temporary directory

  Check the target directory before creation, write members into a uniquely named sibling temporary
  directory, write manifest.json last with member hashes and bundle metadata, then atomically rename
  the temporary directory into place. On any exception remove only the temporary directory.

- [ ] Step 3: Preserve overwrite and portability semantics

  Raise OutputExistsError unless force=True; create parent directories only after the overwrite check;
  use UTF-8; reject non-finite values; and ensure the manifest has no machine-specific paths.

- [ ] Step 4: Run bundle failure-path tests

  Test protected output, force=True, a simulated member-write failure, deterministic repeated output,
  manifest hash verification, and no leftover temporary sibling directory.

### Task 4: Add the thin compare CLI command

Files:
- Modify: src/cpdatakit/cli.py
- Create: tests/test_cli_comparison.py
- Modify: README.md, README.zh-CN.md, docs/roadmap.md, CHANGELOG.md

Interfaces:
- Adds: cpdatakit compare LEFT_REPORT RIGHT_REPORT --output DIRECTORY [--force].

- [ ] Step 1: Add failing CLI tests

  Cover successful bundle creation, invalid JSON/status 2, protected directory, --force, warning/error
  reports remaining comparable, and absence of raw values/absolute paths in members.

- [ ] Step 2: Implement parser and orchestration

  Load the two JSON reports, call compare_reports(), call write_comparison_bundle(), print the output
  directory name, and return 0 for a successful comparison or 2 for parameter/read/output failures.
  A breaking schema or validation result is comparison content, not a command failure.

- [ ] Step 3: Document scope and offline guarantees

  Add copyable commands and state that bundles compare declared schema/validation/aggregate metrics;
  they do not certify physical correctness or compare raw tensor records.

### Task 5: Verify and hand off comparison bundles

Files:
- Read: all changed comparison/report/CLI/test/docs files and the approved spec

- [ ] Step 1: Run the full local quality gate

  Run the full pytest suite with coverage --cov-fail-under=85, Ruff check, Ruff format check,
  reproducible builds, wheel smoke, and existing benchmark diagnostics.

- [ ] Step 2: Audit bundle contents

  Recompute every manifest digest, inspect the four-member allowlist, scan for raw records, absolute
  paths, credential-like values, JavaScript, and external URLs, and verify repeated output is
  byte-identical.

- [ ] Step 3: Keep dataset-level comparison as a separate design

  Do not add full HDF5 comparison or a performance-sensitive streaming algorithm until Issue #4
  evidence and a separate bounded-read design establish memory and scientific semantics.
