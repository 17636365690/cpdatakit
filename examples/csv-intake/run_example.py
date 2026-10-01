"""Import a synthetic semicolon CSV using an installed CPDataKit candidate."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

from cpdatakit.application import ReportRequest, build_report
from cpdatakit.application.csv_intake import prepare_csv, preview_csv
from cpdatakit.exceptions import CPDataKitError
from cpdatakit.io import write_hdf5
from cpdatakit.schema import schema_to_dict
from cpdatakit.validation import validate_dataset


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=Path(__file__).with_name("instrument.csv"))
    parser.add_argument("--settings", type=Path, default=Path(__file__).with_name("settings.json"))
    parser.add_argument("--output", type=Path, required=True, help="A new output directory")
    args = parser.parse_args()
    try:
        if args.output.exists():
            raise FileExistsError("Output directory already exists; choose a new --output path")
        settings = json.loads(args.settings.read_text(encoding="utf-8"))
        payload = args.input.read_bytes()
        preview = preview_csv(payload, settings["options"])
        prepared = prepare_csv(
            payload,
            settings["options"],
            settings["columns"],
            source_name=args.input.name,
            source_sha256=preview["source_sha256"],
        )
        description = settings["confirmed_source_definition"]
        schema = replace(
            prepared.schema,
            conventions={**prepared.schema.conventions, "confirmed_source_definition": description},
        )
        manifest = {**prepared.manifest, "confirmed_source_definition": description}
        validation = validate_dataset(prepared.value, schema)
        args.output.mkdir(parents=True, exist_ok=False)
        source = args.output / "source.csv"
        source.write_bytes(payload)
        prepared.value.source = source
        for name, value in (("schema", schema_to_dict(schema)), ("manifest", manifest)):
            (args.output / f"{name}.json").write_text(
                json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        data = args.output / "data.h5"
        write_hdf5(
            prepared.value,
            data,
            schema,
            validation,
            source_description=description,
            operation_log=["Explicit CSV import", json.dumps(manifest, ensure_ascii=False)],
        )
        for format_name, filename in (("json", "report.json"), ("html", "report.html")):
            report = build_report(
                ReportRequest(data, schema, args.output / filename, format=format_name)
            )
            if not report.ok:
                raise CPDataKitError(report.error.message)
        print(json.dumps({"rows": len(prepared.value.data), "fields": list(prepared.value.data)}))
        return 0
    except (CPDataKitError, OSError, ValueError, KeyError) as exc:
        print(f"CSV example: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
