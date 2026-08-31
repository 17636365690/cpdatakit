# Maintenance

This document records the v0.4.0 release path. Keep `pyproject.toml` and `CITATION.cff` aligned
with the current release. For each authorized release, update the version metadata, `CHANGELOG.md`,
and `CITATION.cff` together, then run every check below before publishing.

## Exact release checklist

1. Run the full supported-Python test matrix: `ubuntu-latest` and `windows-latest`, each with
   Python 3.10, 3.11, 3.12, and 3.13, installing `.[dev]` and running `pytest`.
   The separate `minimum-dependencies` CI job runs Python 3.10 with the lower-bound runtime
   dependency ranges from `pyproject.toml` and the test dependencies needed by the suite.
2. Run the Ubuntu quality gate with Python 3.12:

   ```bash
   pytest --cov=cpdatakit --cov-report=term-missing --cov-fail-under=85
   ruff check .
   ruff format --check .
   ```

   The release gate requires at least 85% coverage.
3. Check the version before building. Build the distributions twice and compare them byte-for-byte.
   The following is the CI-equivalent shell sequence:

   ```bash
   version="$(python -c 'import tomllib; print(tomllib.load(open("pyproject.toml", "rb"))["project"]["version"])')"
   python scripts/check_release.py "v${version}"
   rm -rf dist
   mkdir -p dist/repro-a dist/repro-b
   python -m build --outdir dist/repro-a
   python -m build --outdir dist/repro-b
   python scripts/check_reproducible_build.py dist/repro-a dist/repro-b
   cp dist/repro-a/* dist/
   rm -rf dist/repro-a dist/repro-b
   python scripts/check_release.py "v${version}" --dist-dir dist
   python -m twine check dist/*
   ```

4. Install the wheel into a clean environment and smoke-test the public HDF5 APIs as well as the
   existing CLI path:

   ```bash
   python -m venv wheel-env
   wheel-env/bin/python -m pip install dist/*.whl
   wheel-env/bin/cpdatakit --version
   wheel-env/bin/python -c "import cpdatakit; print(cpdatakit.__version__)"
   wheel-env/bin/python -c "from cpdatakit import load_hdf5, iter_hdf5_chunks; print('HDF5 APIs available')"
   ```

   On Windows, use the corresponding `wheel-env\\Scripts\\python.exe` and
   `wheel-env\\Scripts\\cpdatakit.exe` paths.
5. Run the two HDF5 scaling diagnostics from the checkout:

   ```bash
   python scripts/benchmark_hdf5_read.py --records 100000 --chunk-size 4096 --hdf5-chunk-size 4096
   python scripts/benchmark_hdf5_read.py --records 1000000 --chunk-size 4096 --hdf5-chunk-size 4096
   ```

   Confirm valid JSON and exact record counts for full, selected-field, and chunked reads. Record
   elapsed time and peak RSS for comparison. Timing from one machine provides diagnostic evidence.
6. Complete the existing README commands, deterministic sample regeneration comparison,
   secret/absolute-path scan, license review, and sdist/wheel content inspection. Publish when the
   version in `pyproject.toml`, the installed wheel, the Git tag/release, and PyPI agree in a fresh
   environment.

Review schema changes as public API. Backward-compatible additions may remain in 1.x. Changes to
meaning, units, requiredness, or conventions require a new schema version. Security reports follow
`SECURITY.md`. Fixture contributions use synthetic, openly licensed, or redistribution-approved
solver output.

