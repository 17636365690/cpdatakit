# Thermal-cycle data contract example

This example demonstrates CPDataKit's scientific-data core without crystal-plasticity fields. The
schema declares a `thermal-cycle` profile with elapsed time, absolute temperature, and a categorical
cycle stage. The raw CSV uses minutes and degrees Celsius; the mapping explicitly renames the
exporter fields and converts them to seconds and kelvin.

Run these commands from the repository root. They write outputs to a new `thermal-cycle-output`
directory; remove or rename that directory yourself before repeating the workflow, or add `--force`
to individual file-producing commands when replacement is intentional.

```bash
mkdir thermal-cycle-output
cpdatakit validate examples/thermal-cycle/input/thermal-cycle.csv --schema examples/thermal-cycle/schema/thermal-cycle.json --mapping examples/thermal-cycle/mappings/thermal-cycle.json --json-output thermal-cycle-output/validation.json
cpdatakit summary examples/thermal-cycle/input/thermal-cycle.csv --schema examples/thermal-cycle/schema/thermal-cycle.json --mapping examples/thermal-cycle/mappings/thermal-cycle.json --json-output thermal-cycle-output/summary.json
cpdatakit convert examples/thermal-cycle/input/thermal-cycle.csv --schema examples/thermal-cycle/schema/thermal-cycle.json --mapping examples/thermal-cycle/mappings/thermal-cycle.json --output thermal-cycle-output/thermal-cycle.h5 --source-description "Deterministic thermal-cycle example"
cpdatakit inspect thermal-cycle-output/thermal-cycle.h5 --schema examples/thermal-cycle/schema/thermal-cycle.json --format json --output thermal-cycle-output/inspection.json
cpdatakit report thermal-cycle-output/thermal-cycle.h5 --schema examples/thermal-cycle/schema/thermal-cycle.json --format json --output thermal-cycle-output/report-a.json
cpdatakit report thermal-cycle-output/thermal-cycle.h5 --schema examples/thermal-cycle/schema/thermal-cycle.json --format json --output thermal-cycle-output/report-b.json
cpdatakit compare thermal-cycle-output/report-a.json thermal-cycle-output/report-b.json --output thermal-cycle-output/comparison
cpdatakit plot thermal-cycle-output/thermal-cycle.h5 --schema examples/thermal-cycle/schema/thermal-cycle.json --kind xy --x time --y temperature --output thermal-cycle-output/temperature-vs-time.png
```

The HDF5 file embeds the canonical schema and SHA-256 digest. Validation and comparison establish
declared structural conformance and aggregate equality only; they do not establish thermal-model or
physical correctness.
