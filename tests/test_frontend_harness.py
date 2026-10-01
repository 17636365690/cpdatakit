"""The frontend runner must execute every requested case and observe late failures."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

HARNESS = Path(__file__).with_name("frontend_resource_harness.cjs")
STATIC = Path(__file__).parents[1] / "src/cpdatakit/web/static"


def run_harness(*behaviors, harness=HARNESS):
    node = shutil.which("node")
    assert node is not None, "Node.js is required for frontend verification"
    return subprocess.run(
        [node, str(harness), *behaviors],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=15,
    )


def records(result):
    return [json.loads(line) for line in result.stdout.splitlines()]


def test_harness_runs_every_requested_scenario_with_clean_background_state():
    result = run_harness("selection", "coalesce")
    assert result.returncode == 0, result.stdout + result.stderr
    passed = [item for item in records(result) if item["phase"] == "passed"]
    assert [item["behavior"] for item in passed] == ["selection", "coalesce"]
    assert all(item["pending_timers"] == 0 and item["watching"] == 0 for item in passed)


@pytest.mark.parametrize("behaviors", [(), ("unknown-case",), ("selection", "unknown-case")])
def test_harness_rejects_missing_or_unknown_scenarios(behaviors):
    result = run_harness(*behaviors)
    assert result.returncode != 0, "An unexecuted scenario must never silently pass"
    assert "behavior" in result.stderr.lower()


def test_harness_observes_late_frontend_errors_before_reporting_a_pass(tmp_path):
    harness = tmp_path / "tests" / HARNESS.name
    harness.parent.mkdir()
    shutil.copy2(HARNESS, harness)
    static = tmp_path / "src/cpdatakit/web/static"
    shutil.copytree(STATIC, static)
    with (static / "app.js").open("a", encoding="utf-8") as output:
        output.write("\nsetTimeout(() => { throw new Error('late frontend failure'); }, 50);\n")
    result = run_harness("selection", harness=harness)
    assert result.returncode != 0
    assert "late frontend failure" in result.stderr
    phases = [item["phase"] for item in records(result)]
    assert "started" in phases, "A failure must retain its execution stage"
    assert "passed" not in phases, "A pending callback must finish before success is reported"
