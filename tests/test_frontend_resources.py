"""Execute shipped browser resource interactions without adding a JS dependency."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

BEHAVIORS = [
    "historical",
    "selection",
    "load-more",
    "slice",
    "coalesce",
    "stale-page",
    "schema-selection",
    "slice-legacy",
    "active-history",
    "terminal-refresh-race",
    "stale-running",
    "pending-persistence",
    "validation-context",
    "validation-history",
    "output-conflict",
    "artifact-actions",
    "authoring-context",
    "authoring-save",
    "mapping-scope",
    "authoring-reset",
    "draft-stale",
    "authoring-save-stale",
    "initial-bound-input",
    "activation-refresh-race",
    "activation-user-change",
    "activation-stale-context",
    "activation-overlap",
    "authoring-preview-current",
    "csv-error-hint",
    "csv-settings-reuse",
    "csv-settings-drift",
    "csv-settings-stale-load",
    "csv-settings-invalid-load",
    "csv-settings-submit",
    "csv-settings-custom-role",
    "csv-settings-load-file-change",
    "upload-clears-authoring",
    "csv-edit-summary",
    "csv-reconfirm",
    "csv-blocking",
    "csv-type-switch",
    "csv-server-error",
    "csv-preview-stale",
    "csv-raw-preview",
    "csv-source-collapse",
    "jobs-attention",
    "paging-quiet",
    "check-visibility",
]


@pytest.fixture(scope="module")
def frontend_results():
    """Start Node once; each scenario still has a fresh VM and its own assertions."""
    node = shutil.which("node")
    assert node is not None, "Node.js is required for browser logic verification"
    try:
        result = subprocess.run(
            [node, str(Path(__file__).with_name("frontend_resource_harness.cjs")), *BEHAVIORS],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=15,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = (exc.stdout or b"").decode("utf-8", errors="replace")
        stderr = (exc.stderr or b"").decode("utf-8", errors="replace")
        pytest.fail(f"Frontend runner exceeded 15s; last completed stage:\n{stdout}\n{stderr}")
    assert result.returncode == 0, result.stdout + result.stderr
    records = [json.loads(line) for line in result.stdout.splitlines()]
    passed = [item for item in records if item["phase"] == "passed"]
    assert [item["behavior"] for item in passed] == BEHAVIORS, result.stdout
    print(result.stdout)
    return {item["behavior"]: item for item in passed}


@pytest.mark.parametrize("behavior", BEHAVIORS)
def test_frontend_resource_behavior(behavior, frontend_results):
    result = frontend_results[behavior]
    assert result["pending_timers"] == 0
    assert result["watching"] == 0
