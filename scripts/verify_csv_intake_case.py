"""Opt-in local IN718 acceptance; source measurements are never vendored or edited."""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

from cpdatakit.application import ReportRequest, build_report
from cpdatakit.application.csv_intake import prepare_csv, preview_csv
from cpdatakit.io import load_hdf5, write_hdf5
from cpdatakit.validation import validate_dataset

_SOURCE_SHA256 = json.loads(
    (Path(__file__).parents[1] / "examples/csv-intake/in718-source.json").read_text(
        encoding="utf-8"
    )
)["archive_sha256"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-zip", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    source = args.source_zip.read_bytes()
    digest = hashlib.sha256(source).hexdigest()
    if digest != _SOURCE_SHA256:
        parser.error(
            "Expected the original IN718 05_Mechanical_properties.zip from "
            f"Mendeley 10.17632/nx55jj48rx.2 (SHA-256 {_SOURCE_SHA256}); got {digest}"
        )
    args.output.mkdir(parents=True, exist_ok=False)
    options = {"delimiter": ";", "header_row": 1}
    indices = [0, 1, 2, 4, 5]
    names = ["time", "extension", "force", "reported_stress", "reported_strain"]
    input_units = ["s", "mm", "N", "MPa", "mm/mm"]
    output_units = ["s", "mm", "kN", "MPa", "dimensionless"]
    choices = [
        {
            "index": i,
            "include": True,
            "target": name,
            "dtype": "float",
            "input_unit": unit_in,
            "output_unit": unit_out,
            "role": "measured_quantity",
        }
        for i, name, unit_in, unit_out in zip(
            indices, names, input_units, output_units, strict=True
        )
    ] + [{"index": 3, "include": False}]
    records = []
    with zipfile.ZipFile(io.BytesIO(source)) as archive:
        files = sorted(name for name in archive.namelist() if name.lower().endswith(".csv"))
        assert len(files) == 12, "IN718 acceptance requires all 12 documented CSV files"
        for number, member in enumerate(files, 1):
            payload = archive.read(member)
            preview = preview_csv(payload, options)
            if len(preview["columns"]) != 6:
                raise AssertionError("Expected the documented six-column IN718 export")
            prepared = prepare_csv(
                payload,
                options,
                choices,
                source_name=member,
                source_sha256=preview["source_sha256"],
            )
            raw_path = args.output / f"curve-{number:02d}.csv"
            raw_path.write_bytes(payload)
            prepared.value.source = raw_path
            validation = validate_dataset(prepared.value, prepared.schema)
            assert validation.valid and not validation.warnings, validation.to_dict()
            path = args.output / f"curve-{number:02d}.h5"
            write_hdf5(
                prepared.value,
                path,
                prepared.schema,
                validation,
                source_description=f"Mendeley 10.17632/nx55jj48rx.2; {member}",
                operation_log=[json.dumps(prepared.manifest, ensure_ascii=False)],
            )
            result = load_hdf5(path)
            expected = pd.read_csv(io.BytesIO(payload), sep=";").iloc[:, indices]
            expected.columns = names
            expected["force"] *= 0.001
            assert list(result.data) == names
            np.testing.assert_allclose(
                result.data.to_numpy(), expected.to_numpy(), rtol=1e-15, atol=1e-12
            )
            assert result.metadata["units"] == dict(zip(names, output_units, strict=True))
            assert hashlib.sha256(raw_path.read_bytes()).hexdigest() == preview["source_sha256"]
            if number == 1:
                report = build_report(
                    ReportRequest(path, prepared.schema, args.output / "report.html")
                )
                assert report.ok, report.to_dict()
            records.append(
                {
                    "member": member,
                    "records": len(result.data),
                    "columns": list(result.data),
                    "validation_valid": validation.valid,
                    "source_sha256": preview["source_sha256"],
                    "excluded": prepared.manifest["excluded_columns"],
                    "maximum_absolute_difference": float(
                        np.max(np.abs(result.data.to_numpy() - expected.to_numpy()))
                    ),
                }
            )
    assert hashlib.sha256(args.source_zip.read_bytes()).hexdigest() == digest
    assert sum(row["records"] for row in records) == 24073, "IN718 acceptance requires 24,073 rows"
    summary = {
        "file_count": len(records),
        "records": sum(row["records"] for row in records),
        "source_zip_sha256": digest,
        "source_unchanged": True,
        "column_order_preserved": True,
        "cases": records,
        "scope": (
            "Five unit-labelled reported quantities, fourth unnamed column explicitly excluded. "
            "Not physical validation."
        ),
    }
    (args.output / "acceptance.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {key: value for key, value in summary.items() if key != "cases"}, ensure_ascii=False
        )
    )


if __name__ == "__main__":
    main()
