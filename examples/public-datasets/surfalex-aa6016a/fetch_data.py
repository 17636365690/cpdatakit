"""Fetch and verify the two published Surfalex Workflow 7A source files."""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import sys
import tempfile
from collections.abc import Mapping
from pathlib import Path
from urllib.request import Request, urlopen

SOURCE_FILES = (
    {
        "name": "7A_simulate_uniaxial_tension.yml",
        "url": (
            "https://zenodo.org/records/7307639/files/7A_simulate_uniaxial_tension.yml?download=1"
        ),
        "md5": "3500212694d54f8a974af4c8a9af9b84",
        "sha256": "d548c12dfd7fabf01b3dce4233c00faf5c4bb13e04d5a5bb8e1d7ea77a393abb",
    },
    {
        "name": "7A_workflow.hdf5",
        "url": "https://zenodo.org/records/7307639/files/7A_workflow.hdf5?download=1",
        "md5": "58abe7493d55d8f5e0033ba740e76f8e",
        "sha256": "a4c1c51609e9dadcd3ea680ab6b3511877affac5f24fe25b84daa6daf8fb0693",
    },
)


def _digests(path: Path) -> tuple[str, str]:
    md5 = hashlib.md5()
    sha256 = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            md5.update(block)
            sha256.update(block)
    return md5.hexdigest(), sha256.hexdigest()


def verify_file(path: str | Path, spec: Mapping[str, str]) -> None:
    """Verify one downloaded file against its published MD5 and expected SHA-256."""
    input_path = Path(path)
    try:
        actual_md5, actual_sha256 = _digests(input_path)
    except OSError as exc:
        raise ValueError(f"Cannot hash source file {input_path}: {exc}") from exc
    expected_md5 = spec["md5"].lower()
    expected_sha256 = spec["sha256"].lower()
    if actual_md5 != expected_md5:
        raise ValueError(
            f"{input_path.name} MD5 mismatch: expected {expected_md5}, got {actual_md5}"
        )
    if actual_sha256 != expected_sha256:
        raise ValueError(
            f"{input_path.name} SHA-256 mismatch: expected {expected_sha256}, got {actual_sha256}"
        )


def _download(spec: Mapping[str, str], directory: Path, *, force: bool) -> Path:
    target = directory / spec["name"]
    if target.exists():
        if not target.is_file():
            raise ValueError(f"Existing source path is not a file: {target}")
        try:
            verify_file(target, spec)
        except ValueError as exc:
            if not force:
                raise ValueError(
                    f"Existing source file is different: {target}; pass --force to replace it"
                ) from exc
        else:
            return target

    with tempfile.NamedTemporaryFile(
        mode="wb", prefix=f".{target.name}.", suffix=".download", dir=directory, delete=False
    ) as temporary:
        temporary_path = Path(temporary.name)
    try:
        request = Request(
            spec["url"],
            headers={"User-Agent": "CPDataKit-Surfalex-Reference-Case/1.0"},
        )
        with urlopen(request, timeout=120) as response, temporary_path.open("wb") as output:
            shutil.copyfileobj(response, output, length=1024 * 1024)
        verify_file(temporary_path, spec)
        os.replace(temporary_path, target)
    except BaseException:
        temporary_path.unlink(missing_ok=True)
        raise
    return target


def main(argv: list[str] | None = None) -> int:
    """Download the selected source files into a user-selected directory."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("data"))
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args(argv)
    args.output.mkdir(parents=True, exist_ok=True)
    try:
        downloaded = [_download(spec, args.output, force=args.force) for spec in SOURCE_FILES]
    except (OSError, ValueError) as exc:
        print(f"surfalex fetch: error: {exc}", file=sys.stderr)
        return 2
    for path in downloaded:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
