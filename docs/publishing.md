# Publishing to PyPI

CPDataKit uses PyPI Trusted Publishing so no long-lived PyPI token is stored in GitHub.

## One-time owner setup

1. Sign in to <https://pypi.org/manage/account/publishing/> with two-factor authentication enabled.
2. Create a pending publisher with these exact values:
   - PyPI project name: `cpdatakit`
   - GitHub owner: `17636365690`
   - GitHub repository: `cpdatakit`
   - Workflow name: `publish-pypi.yml`
   - Environment name: `pypi`
3. In GitHub, review the `pypi` environment and keep deployment approval enabled.

## First publication

After the pending publisher exists, run the **Publish to PyPI** workflow manually with tag
`v0.1.0`. The workflow checks out that immutable tag, builds both distributions, runs
`twine check`, and exchanges GitHub's short-lived OIDC identity for a temporary PyPI credential.

Do not rerun a successful version: PyPI distributions are immutable. For later versions, update
`pyproject.toml`, `src/cpdatakit/_version.py`, `CITATION.cff`, and `CHANGELOG.md` together, merge a
green release PR, and publish a GitHub Release. The release event will trigger the same workflow.
