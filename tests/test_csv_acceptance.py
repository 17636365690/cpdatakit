"""A wrong archive must not produce a successful IN718 acceptance receipt."""

import subprocess
import sys
import zipfile
from pathlib import Path


def test_in718_acceptance_rejects_wrong_archive_without_creating_success_evidence(tmp_path):
    source = tmp_path / "empty.zip"
    with zipfile.ZipFile(source, "w"):
        pass
    output = tmp_path / "acceptance"
    script = Path(__file__).parents[1] / "scripts/verify_csv_intake_case.py"
    result = subprocess.run(
        [
            sys.executable,
            "-X",
            "utf8",
            str(script),
            "--source-zip",
            str(source),
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
    )
    assert result.returncode != 0, "An empty archive cannot establish real-case acceptance"
    assert "IN718" in result.stderr
    assert not output.exists()
