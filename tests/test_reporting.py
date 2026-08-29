from __future__ import annotations

from pathlib import Path

import pytest

from cpdatakit.exceptions import OutputExistsError
from cpdatakit.model import Dataset
from cpdatakit.schema import ProfileSchema, load_schema, schema_to_dict
from cpdatakit.validation import validate_dataset


def _build_report_from_dataset(dataset: Dataset, schema: ProfileSchema) -> dict[str, object]:
    result = validate_dataset(dataset, schema)
    return {
        "file": {"filename": "curve.csv", "format": "CSV", "format_version": "not applicable"},
        "schema": schema_to_dict(schema),
        "record_count": len(dataset.data),
        "fields": [
            {
                "name": name,
                "dtype": str(dataset.data[name].dtype),
                "shape": [len(dataset.data)],
                "record_shape": [],
                "unit": schema.field_map()[name].unit,
                "missing_count": int(dataset.data[name].isna().sum()),
                "description": schema.field_map()[name].description,
                "chunks": None,
            }
            for name in dataset.data.columns
        ],
        "validation": result.to_dict(),
        "statistics": {"numeric_fields": {"stress": {"min": 0.0, "max": 1.0}}},
        "provenance": {"input_filename": "curve.csv"},
        "adapter": {},
        "hdf5": {},
        "scope_note": (
            "Validation conformance does not establish physical or scientific correctness."
        ),
    }


def test_report_json_is_sorted_and_newline_terminated() -> None:
    from cpdatakit.reporting import render_report_json

    report = {"z": 1, "a": {"message": "safe"}}

    rendered = render_report_json(report)

    assert rendered == '{\n  "a": {\n    "message": "safe"\n  },\n  "z": 1\n}\n'


def test_report_markdown_has_stable_sections_and_field_order(curve: Dataset) -> None:
    from cpdatakit.reporting import render_report_markdown

    rendered = render_report_markdown(_build_report_from_dataset(curve, load_schema("curve")))

    assert rendered.index("## Fields") < rendered.index("## Validation")
    assert rendered.index("| step |") < rendered.index("| strain |")
    assert (
        "Validation conformance does not establish physical or scientific correctness." in rendered
    )


def test_report_html_escapes_user_strings() -> None:
    from cpdatakit.reporting import render_report_html

    report = {
        "file": {"format": "CSV"},
        "fields": [{"name": "<field>", "description": "<script>alert(1)</script>"}],
        "validation": {
            "errors": [{"message": "bad <value>", "field": "<field>"}],
            "warnings": [],
        },
        "scope_note": "<not trusted>",
    }

    rendered = render_report_html(report)

    assert "&lt;field&gt;" in rendered
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in rendered
    assert "<script>alert(1)</script>" not in rendered
    assert "<script" not in rendered.lower()
    assert "http://" not in rendered


def test_report_contains_errors_warnings_statistics_and_metadata(
    tmp_path: Path,
) -> None:
    from cpdatakit.reporting import build_report

    path = tmp_path / "curve.csv"
    path.write_text(
        "step,strain,stress\n0,0.0,1.0\n0,0.0,1.0\n1,0.1,\n",
        encoding="utf-8",
    )

    report = build_report(path, "curve")

    assert report["validation"]["errors"]
    assert report["validation"]["warnings"]
    assert "numeric_fields" in report["statistics"]
    assert report["provenance"]["input_filename"] == "curve.csv"
    assert "scope_note" in report


def test_report_redacts_paths_and_credentials() -> None:
    from cpdatakit.reporting import render_report_json

    report = {
        "provenance": {
            "input_filename": r"C:\secret\input.h5",
            "source_description": "password=super-secret /home/user/private/input.h5",
            "api_token": "token-value",
        }
    }

    rendered = render_report_json(report)

    assert r"C:\secret" not in rendered
    assert "/home/user/private" not in rendered
    assert "super-secret" not in rendered
    assert "token-value" not in rendered


def test_report_markdown_is_deterministic(curve: Dataset) -> None:
    from cpdatakit.reporting import render_report_markdown

    report = _build_report_from_dataset(curve, load_schema("curve"))

    assert render_report_markdown(report) == render_report_markdown(report)


def test_report_json_renderer_rejects_non_finite_values() -> None:
    from cpdatakit.reporting import render_report_json

    with pytest.raises(ValueError):
        render_report_json({"value": float("inf")})


def test_write_report_protects_existing_output(curve: Dataset, tmp_path: Path) -> None:
    from cpdatakit.reporting import write_report

    target = tmp_path / "report.md"
    target.write_text("original", encoding="utf-8")
    report = _build_report_from_dataset(curve, load_schema("curve"))

    with pytest.raises(OutputExistsError):
        write_report(report, target, format="markdown")

    write_report(report, target, format="markdown", force=True)
    assert target.read_text(encoding="utf-8").startswith("# CPDataKit Validation Report")


def test_build_report_from_hdf5_includes_hdf5_chunk_info(curve: Dataset, tmp_path: Path) -> None:
    from cpdatakit.io import write_hdf5
    from cpdatakit.reporting import build_report

    schema = load_schema("curve")
    input_path = tmp_path / "curve.h5"
    write_hdf5(curve, input_path, schema, validate_dataset(curve, schema), hdf5_chunk_size=2)

    report = build_report(input_path, schema)

    assert report["hdf5"]["chunks"]["step"] == [2]
    assert report["schema"]["profile"] == "curve"
    assert report["record_count"] == 3
