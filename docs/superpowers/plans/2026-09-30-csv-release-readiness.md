# CSV release readiness implementation plan

> Execution: complete the user's authorized local work in this chat; retain all prior files and stop before commit, push, tag or publication.

**Goal:** Deliver a tested CSV candidate with preserved sources, an installed-package first-use example and evidence-qualified CI diagnosis.

**Architecture:** Keep the existing CSV intake, catalog and immutable result contracts. Change only the frontend test runner's lifecycle and CSV error presentation; add a small synthetic example and release evidence. Do not restructure format adapters.

**Tech stack:** Python >=3.12, existing dependency ranges, Node 22/24 for frontend checks, installed wheel and Chromium for acceptance.

**Spec:** `docs/superpowers/specs/2026-09-29-csv-workflow.md` plus the user's 2026-09-30 completion criteria.

## Constraints and baseline

- Public main and latest release verified as f2cd9e5 / v0.9.3. Current development version stays 0.9.3 until a release version is approved.
- Preserve the 25 incoming dirty files; snapshot and SHA-256 inventory are in `.artifacts/csv-release-20260930/intake-state.json`.
- Work in `codex/csv-release-readiness-20260930`; preserve sibling worktrees.
- No timeout increase, skip, assertion removal, service configuration change or experimental source modification.
- Native NetCDF3 and datetime coordinates remain separately recorded limitations.

## 1. Frontend harness lifecycle

Files: `tests/frontend_resource_harness.cjs`, `tests/test_frontend_resources.py`, new `tests/test_frontend_harness.py`, both test workflows.

- [x] Obtain failing Windows 3.12/latest artifacts, source distribution, dependency identities and adjacent passing Windows artifacts.
- [x] Run the original and candidate harness with stage instrumentation using Node 22.23.2 and Node 24.18.0; retain 120-run timings and natural process-exit evidence.
- [x] Add subprocess regression tests: two requested scenarios each produce a pass record; unknown scenarios fail; delayed frontend errors cannot be reported as passes.
- [x] Observe failures before changes, then implement serial scenarios with fresh VM contexts and drain each scenario's tracked timers/polling. Retain the 15-second subprocess limit and every existing assertion.
- [x] Use one module-scoped invocation; require a complete passing record for every parametrized pytest case. Include partial stage output on failures/timeouts.
- [x] Record Node/platform identity in CI; rerun the targeted tests and installed dependency environment.

## 2. CSV error guidance

Files: `src/cpdatakit/web/static/csv-intake.js` and the frontend harness/tests.

- [x] Add a test that returns an actual API-shaped CSV parse error with a row diagnostic and Chinese corrective hint; assert both reach the visible status.
- [x] Observe the missing-hint failure, then display the message and hint in both CSV handlers.
- [x] Verify invalid imports do not create dataset records or silently drop rows.

## 3. First-use example and documentation

Files: new `examples/csv-intake/` and `tests/test_csv_example.py`; README pair, quickstart and workbench guide.

- [x] Test the runnable synthetic semicolon example against independently specified values, source bytes, units, column order and report validity; reject bad input without creating output and refuse output replacement.
- [x] Implement the small installed-package example using existing intake APIs. Include settings, source-definition text and byte-preserved source output.
- [x] Document clean Windows/POSIX installation, the exact field table, resulting files and error correction. Distinguish unpublished candidate features from PyPI v0.9.3.

## 4. Acceptance and release handoff

Files: new verification record and `.github/release-notes/v0.10.0-draft.md`.

- [x] Reconcile the original IN718 archive/12 files/24,073 rows against the prior receipt; independently rerun all cases and preservation checks.
- [x] Run full Windows tests with coverage, lint/format/JS checks and release metadata checks.
- [x] Build wheel/sdist, check reproducibility/metadata, install the exact wheel into a fresh runtime, check imports and dependencies.
- [x] Exercise the packaged workbench in Chromium: malformed input, six-column preview, field/type/role/unit confirmation, import/report, conversion, bound-schema reuse, idempotence and reload. Read back values, raw bytes and hashes.
- [x] Keep historical, current, unverified and failed results separate. Suggest v0.10.0 because CSV confirmation and artifact reuse add functionality; remote candidate CI remains pending user-authorized push.
