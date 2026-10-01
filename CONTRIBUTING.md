# Contributing

Open an issue before large schema or adapter changes. Fork the project, create a focused branch,
add tests and documentation, then run `pytest`, `ruff check .`, `ruff format --check .`, and
`python -m build`. Contributions are submitted under Apache-2.0.

Frontend tests require Node.js on PATH. This candidate was verified with Node 22.23.2 and
24.18.0; a missing runtime fails verification. Workbench users do not need Node.js.
Installed-wheel browser checks use Playwright 1.63.0 and Chromium in a separate test environment.

Use synthetic, openly licensed, or redistribution-approved fixtures. Keep ODB files, confidential
research data, secrets, personal paths, and commercial installation details out of commits.
Record scientific conventions explicitly in the schema or mapping so units and measures remain
reviewable.

