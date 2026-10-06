"""Public scientific context must survive redaction without exposing local secrets."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cpdatakit.inspection import sanitize_error_message, sanitize_for_output
from cpdatakit.reporting import render_report_html, render_report_json, render_report_markdown


@pytest.mark.parametrize(
    "text",
    [
        "https://doi.org/10.1039/D2CP04680F",
        "Reference https://example.org/a/(b)/c?figure=1#data",
        "Source http://example.org/dataset/17",
        "0.1 mol / l; scan rate 50 mV / s",
        "mol /l",
        "mol/ l",
        "1 / s",
        "kg / m**3",
        "Rate kg / m / s**2; source https://example.org/data",
    ],
)
def test_scientific_context_is_preserved_and_redaction_is_idempotent(text: str) -> None:
    metadata = {"provenance": {"source_description": text}}

    safe = sanitize_for_output(metadata)

    assert safe == metadata
    assert sanitize_for_output(safe) == safe
    assert sanitize_error_message(text) == text


@pytest.mark.parametrize(
    "path",
    [
        r"C:\Lab Data\sample.csv",
        r"\\server\Lab Data\sample.csv",
        "/home/alice/Lab Data/sample.csv",
        "/tmp",
        r"C:\Lab mV / s\sample.csv",
        "/home/alice/Lab mV / s/sample.csv",
        "file:///home/alice/sample.csv",
    ],
)
def test_public_context_does_not_exempt_adjacent_private_paths(path: str) -> None:
    public = "https://doi.org/10.1039/D2CP04680F; unit mol / l; "
    raw = {"source_description": public + path, "api_token": "fake-token"}

    safe = sanitize_for_output(raw)

    assert safe["source_description"].startswith(public)
    assert "[path]" in safe["source_description"]
    for private in ("Lab Data", "sample.csv", "alice", "server", "/tmp"):
        assert private not in safe["source_description"]
    assert safe["api_token"] == "[redacted]"
    assert sanitize_for_output(safe) == safe


@pytest.mark.parametrize(
    ("url", "forbidden"),
    [
        (
            "https://alice:fake-pass@example.org/data?token=fake-secret&view=full",
            ["alice", "fake-pass", "fake-secret"],
        ),
        ("https://example.org/data?t%6fken=fake-secret&view=full", ["fake-secret"]),
        (
            "https://example.org/data?file=/home/alice/private.csv&view=full",
            ["alice", "private.csv"],
        ),
        (
            "https://example.org/data?file=C:/Lab%20Data/private.csv&view=full",
            ["Lab", "private.csv"],
        ),
        ("https://example.org/data?view=full#access_token=fake-secret", ["fake-secret"]),
    ],
)
def test_preserved_urls_still_redact_credentials_and_local_path_parameters(
    url: str, forbidden: list[str]
) -> None:
    safe = sanitize_for_output({"source_description": url})["source_description"]

    assert safe.startswith("https://example.org/data?")
    assert "view=full" in safe
    assert all(secret not in safe for secret in forbidden)
    assert sanitize_error_message(safe) == safe


@pytest.mark.parametrize(
    ("suffix", "forbidden"),
    [
        ("#token:fake-secret", "fake-secret"),
        ("?token:fake-secret", "fake-secret"),
        ("#C:/Lab/private.csv", "private.csv"),
        ("?/home/alice/private.csv", "alice"),
        ("#token%3Afake-secret", "fake-secret"),
    ],
)
def test_unkeyed_url_query_and_fragment_still_redact_private_content(
    suffix: str, forbidden: str
) -> None:
    safe = sanitize_error_message("https://example.org/data" + suffix)

    assert safe.startswith("https://example.org/data")
    assert forbidden not in safe
    assert sanitize_error_message(safe) == safe


def test_ordinary_url_anchor_is_retained() -> None:
    uri = "https://example.org/data#ordinary-anchor"
    assert sanitize_error_message(uri) == uri


@pytest.mark.parametrize("path", [r"C:\Lab Data\private.csv", r"\\server\Lab Data\private.csv"])
def test_uri_immediately_followed_by_private_path_does_not_hide_its_start(path: str) -> None:
    uri = "https://doi.org/10.1039/D2CP04680F"

    safe = sanitize_for_output({"source_description": uri + ";" + path})

    assert uri in safe["source_description"]
    assert "[path]" in safe["source_description"]
    assert "Lab" not in safe["source_description"]
    assert "private.csv" not in safe["source_description"]
    assert "server" not in safe["source_description"]


def test_path_before_public_reference_does_not_swallow_reference_and_units() -> None:
    uri = "https://doi.org/10.1039/D2CP04680F"
    text = f"Local /home/alice/Lab Data/private.csv; Reference {uri}; unit mol / l"

    safe = sanitize_error_message(text)

    assert uri in safe
    assert "mol / l" in safe
    assert "alice" not in safe and "private.csv" not in safe
    assert sanitize_error_message(safe) == safe


@pytest.mark.parametrize("render", [render_report_json, render_report_markdown, render_report_html])
def test_report_formats_preserve_public_context_and_remove_local_secrets(render) -> None:
    report = {
        "provenance": {
            "source_description": (
                "https://doi.org/10.1039/D2CP04680F\n"
                "0.1 mol / l; scan 50 mV / s\n"
                "Local /home/alice/private data.csv\npassword=fake-password"
            )
        }
    }

    rendered = render(report)

    for public in ("https://doi.org/10.1039/D2CP04680F", "mol / l", "mV / s"):
        assert public in rendered
    for secret in ("alice", "private data.csv", "fake-password"):
        assert secret not in rendered


def test_hdf5_report_pipeline_retains_citation_and_unit_expressions(curve, tmp_path: Path) -> None:
    from cpdatakit.io import write_hdf5
    from cpdatakit.reporting import build_report
    from cpdatakit.schema import load_schema
    from cpdatakit.validation import validate_dataset

    schema = load_schema("curve")
    path = tmp_path / "context.h5"
    description = "Reference https://doi.org/10.1039/D2CP04680F; scan 50 mV / s"
    write_hdf5(curve, path, schema, validate_dataset(curve, schema), source_description=description)

    stored = json.loads(render_report_json(build_report(path, schema)))

    assert stored["provenance"]["source_description"] == description
