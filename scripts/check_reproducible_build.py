"""Compare two distribution directories byte-for-byte."""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _digests(directory: Path) -> dict[str, str]:
    if not directory.is_dir():
        raise FileNotFoundError(f"Distribution directory does not exist: {directory}")
    return {path.name: _sha256(path) for path in sorted(directory.iterdir()) if path.is_file()}


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print("usage: check_reproducible_build.py FIRST_DIR SECOND_DIR", file=sys.stderr)
        return 2

    first = _digests(Path(argv[1]))
    second = _digests(Path(argv[2]))
    if first != second:
        print("Reproducible distribution check failed:", file=sys.stderr)
        print(f"first:  {first}", file=sys.stderr)
        print(f"second: {second}", file=sys.stderr)
        return 1

    print(f"Reproducible distribution check passed: {len(first)} files match")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
