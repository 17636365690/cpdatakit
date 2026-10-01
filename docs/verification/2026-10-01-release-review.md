# CPDataKit v0.10.0 release review — 2026-10-01

Status: local application, installation and browser checks passed; final source-distribution privacy
rebuild and hosted CI remain gates. No push, version tag, GitHub Release or PyPI upload has occurred
at the time this report snapshot was prepared.

## Provenance and preservation

The incoming branch was `codex/csv-release-readiness-20260930`, based on
`f2cd9e5648f272287065f3fe20e2391b49bd5ca6` (v0.9.3). All 43 modified/untracked candidate files
matched the SHA-256 inventory in the previous delivery manifest. Their bytes and the tracked diff
were snapshotted in the original checkout's ignored `.artifacts/release-review-20261001/` directory.
The original branch, HEAD, index and candidate files were preserved. This review uses the separate
`codex/release-v0100-20261001` worktree; sibling projects and worktrees are outside the release scope.

The old origin URL and the authorized `koocmitwho/cpdatakit` URL resolve to GitHub repository ID
1331649261. Remote main was independently checked at the base above. Existing tags/releases end
at v0.9.3. The existing publish workflow accepts semantic version tags on main and uses its existing
`pypi` environment and OIDC publisher. Main requires a PR and seven CI contexts; no protection,
credential, network configuration or workflow publishing permission is changed by this candidate.

v0.10.0 is a minor release because CSV confirmation and reusable conversion inputs add public
workflows. Existing HDF5 1.0 contracts, supported Python versions, runtime dependency ranges and
Apache-2.0 licensing remain unchanged. Package metadata, citation, changelog, release notes and
maintained installation entries were aligned. Active CSV documentation was updated to describe
the release; historical validation records and the earlier draft remain historical evidence.

## Review and fresh evidence

Review covered explicit CSV declarations, numeric precision/overflow rejection, retained sources,
transactional dataset/schema registration, CSRF, project boundaries, linked/changed snapshot
rejection, idempotent reuse, stale frontend responses and HDF5 field ordering. The incoming
frontend runner retains its 15-second limit and observes delayed failures. No new product features
were added during this review.

The independent Windows Python 3.12.13 / Node 24.18.0 run completed with **1558 passed,
1 skipped, 40 warnings**, in **249.70 seconds**, and **90.172048% line coverage** (7652/8486;
gate 85%). The skip is the existing Windows symlink case. This is new evidence for the application
candidate, not the earlier 1558-pass run. Logs, JUnit and coverage are in the review worktree's
ignored `.artifacts/release-review-20261001/`. Ruff and formatting passed; release metadata matches
v0.10.0. Subsequent documentation-only alignment will be checked again by the final commit's CI.

Incoming changed text was scanned for credentials, private keys and personal absolute paths with
no matches. No raw IN718 archive, local browser workspace, research data, weights, virtual
environment or local installation report is intended for the commit or either distribution.
The IN718 example vendors only a source fingerprint and a synthetic three-row CSV. Existing
licensed public fixtures retain their attribution. Live DataCite metadata reconfirmed CC BY 4.0.
A fresh PyPI query confirmed v0.9.3 exists and v0.10.0 did not exist before this release.

The first sdist inspection found a pre-existing historical planning document containing personal
machine paths. Its exact path is excluded from sdist in `pyproject.toml`; the historical repository
record is preserved. This is a necessary packaging privacy correction, with no runtime change.
The final rebuild must verify exclusion and scan all remaining distribution members.

Both initial builds were byte-identical, release/distribution metadata and twine passed. A fresh
Python 3.12.10 runtime installed the exact v0.10.0 wheel without development dependencies;
`pip check`, version/import identity and 18 CLI/API commands passed. The synthetic CSV example
preserved source bytes and produced JSON/HTML reports; regenerated CSV/JSON samples matched
repository fixtures byte-for-byte. Thermal-cycle validation, conversion and plotting also passed.
Direct runtime dependency license metadata and bundled license files were reviewed; dependencies
are installed separately and are not vendored into CPDataKit.

Fresh IN718 reconciliation verified the unchanged licensed archive hash, all 12 CSV files and
24,073 rows, declared units, values, field order and source bytes. Clean-wheel Chromium
153.0.8010.12 / Playwright 1.63.0 acceptance passed for the synthetic three-row CSV, the real
1,865-row CSV and the original upload/validate/convert/report/download workflow. Both CSV cases
passed malformed-input rejection, unit confirmation, source downloads, result reuse, repeated
reuse, reload and ordinary-upload authoring reset. Real browser read-back maximum absolute
difference was 8.881784197001252e-16 kN (rtol 1e-15, atol 1e-12); all reports were valid. All three
test servers exited with code 0. The 100,000/1,000,000-record HDF5 diagnostics returned exact
counts for full, selected and chunked reads; Windows peak RSS is unavailable.

After documentation/packaging adjustments, 20 release-metadata/example tests passed; Ruff,
formatting, JavaScript syntax, release metadata and diff checks passed again.

## Publication gate and limits

A final privacy-safe reproducible rebuild and final-commit Linux/Windows/macOS CI remain gates
at this report snapshot. A tag must not be pushed until these gates pass. Hosted dependency-matrix
checks must include Windows Python 3.12/latest; historical Node timeout results are not evidence
for this candidate. Publication results and exact remote links are recorded separately after the
remote runs reach terminal states.

The historical NetCDF3/date-coordinate limitation is outside this CSV change and remains
documented in `docs/known-issues/netcdf3-datetime.md`; it is not newly verified here. Hash checks
do not lock out an external writer after the final check. CSV validation checks declared contracts
and numeric transformations, and does not establish physical validity of experimental results.
