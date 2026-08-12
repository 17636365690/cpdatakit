from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from cpdatakit import __version__

ROOT = Path(__file__).resolve().parents[1]


def test_release_metadata_is_synchronized() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_release.py"), f"v{__version__}"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == f"Release metadata match v{__version__}"


def test_release_metadata_rejects_non_tag_ref() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_release.py"), "main"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "semantic-version tag" in result.stderr


def test_release_metadata_rejects_noncanonical_version() -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "check_release.py"), "v01.1.1"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "semantic-version tag" in result.stderr
