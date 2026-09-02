from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_application_service_document_covers_cli_shared_use_cases() -> None:
    text = (ROOT / "docs" / "application-services.md").read_text(encoding="utf-8")
    required = (
        "import and inspect",
        "resolve schema and mapping",
        "validate and summarize",
        "convert and write",
        "build reports and comparisons",
        "plot declared fields",
        "capability discovery",
        "CLI",
        "Web",
        "Python API",
    )

    assert all(item in text for item in required)
    assert "argparse" in text and "templates" in text


def test_local_ui_security_document_covers_boundary_invariants() -> None:
    text = (ROOT / "docs" / "local-ui-security.md").read_text(encoding="utf-8")
    required = (
        "loopback",
        "host validation",
        "session token",
        "CSRF",
        "path containment",
        "upload size",
        "archive traversal",
        "overwrite",
        "job cancellation",
        "SQLite",
        "no outbound requests",
        "no telemetry",
        "no cloud account",
    )

    assert all(item in text for item in required)
    assert "TODO" not in text and "TBD" not in text
