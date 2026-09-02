from __future__ import annotations

import inspect
import json
from pathlib import Path

import cpdatakit
from cpdatakit.cli import _parser
from cpdatakit.io import _SUPPORTED
from cpdatakit.schema import BUILTIN_PROFILES, schema_sha256

SNAPSHOT = Path(__file__).parent / "compat" / "v0.5-public-contract.json"


def _command_actions(parser) -> dict[str, list[str]]:
    commands = next(action for action in parser._actions if action.dest == "command")
    result: dict[str, list[str]] = {}
    for name, command in commands.choices.items():
        result[name] = sorted(
            option
            for action in command._actions
            for option in action.option_strings
            if option != "-h"
        )
    return result


def test_v05_public_contract_snapshot_is_unchanged() -> None:
    expected = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    signatures = {
        name: str(inspect.signature(getattr(cpdatakit, name)))
        for name in expected["callable_signatures"]
    }
    actual = {
        "package_exports": sorted(cpdatakit.__all__),
        "callable_signatures": signatures,
        "cli_commands": _command_actions(_parser()),
        "builtin_profiles": sorted(BUILTIN_PROFILES),
        "builtin_schema_hashes": {
            profile: schema_sha256(profile) for profile in sorted(BUILTIN_PROFILES)
        },
        "hdf5": {
            "format_version": "1.0",
            "required_root_attributes": [
                "format",
                "format_version",
                "profile",
                "schema_version",
                "units_json",
                "field_mapping_json",
                "provenance_json",
                "validation_summary_json",
            ],
            "supported_extensions": sorted(_SUPPORTED),
        },
    }

    assert actual["package_exports"] == expected["package_exports"]
    assert actual["callable_signatures"] == expected["callable_signatures"]
    assert actual["builtin_profiles"] == expected["builtin_profiles"]
    assert actual["builtin_schema_hashes"] == expected["builtin_schema_hashes"]
    assert actual["hdf5"] == expected["hdf5"]
    for command, options in expected["cli_commands"].items():
        assert actual["cli_commands"][command] == options
