# Publishing to PyPI

CPDataKit uses PyPI Trusted Publishing with short-lived OIDC credentials managed by GitHub.

## Reproducible distributions

The build backend is pinned in `pyproject.toml`, and CI sets `SOURCE_DATE_EPOCH` from the
source commit used for the build. The quality and PyPI workflows build both distributions twice
and compare their SHA-256 digests before either copy is inspected or uploaded. This catches
timestamp, file-order, or backend drift before a release is published.

## One-time owner setup

1. Sign in to <https://pypi.org/manage/account/publishing/> with two-factor authentication enabled.
2. Create a pending publisher with these exact values:
   - PyPI project name: `cpdatakit`
   - GitHub owner: `17636365690`
   - GitHub repository: `cpdatakit`
   - Workflow name: `publish-pypi.yml`
   - Environment name: `pypi`
3. In GitHub, review the preconfigured `pypi` environment and keep deployment approval enabled.

## First publication

After the pending publisher exists and the release commit is tagged, open the workflow on the
`main` branch and run **Publish to PyPI** manually with the release tag. The workflow and the `pypi`
environment accept dispatches from `main`, require an existing tag on that branch, and compare all
release metadata before building. They build both distributions from the exact tag and run
`twine check`. They exchange GitHub's short-lived OIDC identity for a temporary PyPI credential.
Review the queued `pypi` deployment after confirming the tag and build job. When the workflow succeeds, verify
a clean `pip install cpdatakit==<version>`, then publish the matching GitHub Release with the
already-verified distributions. Keep the PyPI workflow and GitHub Release publication as two
explicit steps so each artifact has a clear verification point.

Each version is published once because PyPI distributions are immutable. For later versions, update
`pyproject.toml`, `src/cpdatakit/_version.py`, `CITATION.cff`, and `CHANGELOG.md` together, merge a
green release PR, tag the release commit, publish and verify PyPI, then publish the matching GitHub
Release.
