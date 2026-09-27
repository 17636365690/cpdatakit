"""Comparison text and recorded diff verification retain inspectable results."""

import json
from pathlib import Path

from cpdatakit.comparison import compare_reports, render_comparison_markdown

ROOT = Path(__file__).parents[1]


def test_comparison_contents_has_exact_sentence_without_trailing_space():
    result = compare_reports({}, {})
    expected = (
        "This comparison covers declared schema, validation, structure, and descriptive aggregates."
    )
    assert result["scope_note"] == expected
    rendered = render_comparison_markdown(result)
    assert rendered.split("## Comparison contents\n\n", 1)[1] == expected + "\n"


def test_diff_check_evidence_records_command_exit_code_and_streams():
    path = ROOT / "docs/verification/2026-09-27-review-fixes/final-diff-check.txt"
    text = path.read_text(encoding="utf-8")
    assert text.strip(), "The diff verification evidence must contain the executed check result"
    result = json.loads(text)
    assert result["command"] == ["git", "diff", "--check"]
    assert result["exit_code"] == 0
    assert isinstance(result["stdout"], str)
    assert isinstance(result["stderr"], str)
    assert len(result["head"]) == 40
