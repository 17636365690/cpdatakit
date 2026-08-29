from __future__ import annotations

import json
import subprocess
import sys


def test_benchmark_reports_storage_chunk_size(tmp_path) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/benchmark_hdf5_read.py",
            "--records",
            "100",
            "--chunk-size",
            "16",
            "--hdf5-chunk-size",
            "8",
            "--output-dir",
            str(tmp_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["records"] == 100
    assert payload["chunk_size"] == 16
    assert payload["hdf5_chunk_size"] == 8
    assert payload["full"]["record_count"] == 100
    assert payload["selected_fields"]["record_count"] == 100
    assert payload["chunked"]["record_count"] == 100
