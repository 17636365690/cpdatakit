"""Validate the README users receive in the built package, not source syntax."""

import importlib.util
import io
import tarfile
import zipfile
from pathlib import Path

import pytest


def _checker():
    path = Path(__file__).parents[1] / "scripts/check_release.py"
    spec = importlib.util.spec_from_file_location("release_link_check", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _distributions(directory, readme):
    metadata = ("Metadata-Version: 2.1\nName: cpdatakit\nVersion: 0.10.1\n\n" + readme).encode()
    with zipfile.ZipFile(directory / "cpdatakit-0.10.1-py3-none-any.whl", "w") as archive:
        archive.writestr("cpdatakit-0.10.1.dist-info/METADATA", metadata)
    with tarfile.open(directory / "cpdatakit-0.10.1.tar.gz", "w:gz") as archive:
        member = tarfile.TarInfo("cpdatakit-0.10.1/PKG-INFO")
        member.size = len(metadata)
        archive.addfile(member, io.BytesIO(metadata))


def test_built_readme_rejects_pypi_relative_document_links(tmp_path):
    _distributions(tmp_path, "First use: [CSV](examples/csv-intake/README.md).")
    with pytest.raises(ValueError, match=r"relative.*link|link.*relative"):
        _checker().verify_distributions(tmp_path, "0.10.1")


def test_built_readme_accepts_absolute_release_links(tmp_path):
    _distributions(
        tmp_path,
        "[CSV](https://github.com/koocmitwho/cpdatakit/blob/v0.10.1/examples/csv-intake/README.md)",
    )
    _checker().verify_distributions(tmp_path, "0.10.1")
