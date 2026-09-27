"""Reproduce the six-test assertion audit, optionally replacing verifiers with no-ops."""

import argparse
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
TARGETS = {
    "tests/test_v06_dependency_matrix.py": [
        "test_matrix_rejects_silent_installed_version_drift",
        "test_probe_completeness_uses_frozen_candidate_list",
        "test_installed_module_accepts_normalized_environment_path",
        "test_installed_module_accepts_symlink_alias",
    ],
    "tests/test_surfalex_public_reference_case.py": [
        "test_fetch_verifier_checks_md5_and_sha256",
        "test_fetch_verifier_rejects_wrong_digest",
    ],
}


def wrapped_loader(original):
    def load(*args, **kwargs):
        module = original(*args, **kwargs)
        for name in (
            "verify_installed",
            "verify_probe",
            "verify_environment_module",
            "verify_file",
        ):
            if hasattr(module, name):
                setattr(module, name, lambda *args, **kwargs: None)
        return module

    return load


class Probe:
    def __init__(self, *, historical, mutate):
        self.historical = historical
        self.mutate = mutate

    def pytest_collection_modifyitems(self, items):
        namespaces = {}
        for item in items:
            path = Path(item.path)
            if path not in namespaces:
                namespace = vars(item.module)
                if self.historical:
                    source = subprocess.check_output(
                        ["git", "show", "6122189:" + path.relative_to(ROOT).as_posix()],
                        cwd=ROOT,
                    )
                    namespace = {"__file__": str(path), "__name__": item.module.__name__}
                    exec(compile(source, str(path), "exec"), namespace)
                if self.mutate:
                    for name in ("_load_matrix_module", "_load_case_module"):
                        if name in namespace:
                            namespace[name] = wrapped_loader(namespace[name])
                namespaces[path] = namespace
            if self.historical:
                item.obj = namespaces[path][item.name]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--historical", action="store_true")
    parser.add_argument("--mutate", action="store_true")
    args = parser.parse_args()
    targets = [str(ROOT / file) + "::" + name for file, names in TARGETS.items() for name in names]
    raise SystemExit(pytest.main(["-q", *targets], plugins=[Probe(**vars(args))]))
