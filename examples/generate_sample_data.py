"""Regenerate all synthetic demonstration datasets with a fixed seed."""

from __future__ import annotations

import argparse
from pathlib import Path

from cpdatakit.samples import generate_sample_data


def main() -> None:
    """Run the sample generator command."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("sample_data"))
    generate_sample_data(parser.parse_args().output)


if __name__ == "__main__":
    main()
