# Maintenance

For every release, run the supported-Python OS matrix, Ruff, package build, wheel installation,
README commands, sample regeneration comparison, secret/absolute-path scan, license review, and
sdist/wheel content inspection. Update `CHANGELOG.md`, version, and `CITATION.cff` together.

Review schema changes as public API: backward-compatible additions may remain in 1.x; changed
meaning, units, requiredness, or conventions require a new schema version. Security reports follow
`SECURITY.md`. Maintainers must not accept real or restricted solver output as fixtures.

