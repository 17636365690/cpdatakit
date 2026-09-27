"""Text writers publish complete contents and preserve prior outputs on failure."""

import os
import stat
import subprocess
from pathlib import Path

import pytest

from cpdatakit.exceptions import CPDataKitError
from cpdatakit.inspection import write_inspection
from cpdatakit.reporting import write_report
from cpdatakit.schema import load_schema, schema_to_json, write_schema


@pytest.fixture(params=["inspection", "report", "schema"])
def writer(request):
    def write(target, force=False):
        if request.param == "inspection":
            return write_inspection({"record_count": 3}, target, format="json", force=force)
        if request.param == "report":
            return write_report({"record_count": 3}, target, format="html", force=force)
        return write_schema(load_schema("curve"), target, force=force)

    return write


@pytest.mark.parametrize("existing", [False, True])
def test_interrupted_text_write_preserves_complete_target(tmp_path, monkeypatch, writer, existing):
    target = tmp_path / "output.txt"
    if existing:
        target.write_bytes(b"previous complete output")
    original = Path.write_text

    def interrupted(path, data, *args, **kwargs):
        if path.parent == tmp_path:
            original(path, "partial output", *args, **kwargs)
            raise OSError("injected interrupted write")
        return original(path, data, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", interrupted)
    with pytest.raises((CPDataKitError, OSError), match="interrupted write"):
        writer(target, force=existing)
    if existing:
        assert target.read_bytes() == b"previous complete output"
    else:
        assert not target.exists()
    assert list(tmp_path.glob(".output.txt.*")) == []


def test_concurrent_text_target_is_preserved(tmp_path, monkeypatch, writer):
    target = tmp_path / "output.txt"
    original = Path.write_text

    def competing(path, data, *args, **kwargs):
        if path.parent == tmp_path:
            target.write_bytes(b"concurrent complete output")
        return original(path, data, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", competing)
    with pytest.raises(CPDataKitError, match="already exists"):
        writer(target)
    assert target.read_bytes() == b"concurrent complete output"
    assert list(tmp_path.glob(".output.txt.*")) == []


def test_text_writer_preserves_mode_and_force_contract(tmp_path, writer):
    target = tmp_path / "output.txt"
    target.write_bytes(b"old")
    target.chmod(0o640)
    before = stat.S_IMODE(target.stat().st_mode)
    with pytest.raises(CPDataKitError, match="already exists"):
        writer(target)
    assert target.read_bytes() == b"old"
    assert writer(target, force=True) == target
    assert target.read_bytes() != b"old"
    assert stat.S_IMODE(target.stat().st_mode) == before
    assert list(tmp_path.glob(".output.txt.*")) == []


def test_new_text_file_uses_normal_create_permissions(tmp_path, writer):
    reference = tmp_path / "reference.txt"
    reference.write_text("reference", encoding="utf-8")
    target = tmp_path / "output.txt"
    writer(target)
    assert stat.S_IMODE(target.stat().st_mode) == stat.S_IMODE(reference.stat().st_mode)


def test_schema_writer_preserves_platform_newlines(tmp_path):
    target = tmp_path / "schema.json"
    schema = load_schema("curve")
    write_schema(schema, target)
    assert target.read_bytes() == schema_to_json(schema).replace("\n", os.linesep).encode("utf-8")


def _saved_acl(path, destination):
    subprocess.run(
        ["icacls", str(path), "/save", str(destination), "/q"], capture_output=True, check=True
    )
    return destination.read_text(encoding="utf-16-le").splitlines()[1]


@pytest.mark.parametrize("protected", [False, True])
def test_permissions_are_preserved_before_content_write(tmp_path, monkeypatch, writer, protected):
    target = tmp_path / "output.txt"
    target.write_bytes(b"previous complete output")
    target.chmod(0o600)
    previous_mode = stat.S_IMODE(target.stat().st_mode)
    if os.name == "nt":
        subprocess.run(
            ["icacls", str(target), "/grant", "*S-1-1-0:(RX)"], capture_output=True, check=True
        )
        if protected:
            subprocess.run(
                ["icacls", str(target), "/inheritance:d"], capture_output=True, check=True
            )
        expected_acl = _saved_acl(target, tmp_path / "original.acl")
    original = Path.write_text
    observed = []

    def checked_write(path, text, *args, **kwargs):
        if path.parent == tmp_path and path.name.startswith(".output.txt."):
            assert stat.S_IMODE(path.stat().st_mode) == previous_mode
            if os.name == "nt":
                assert _saved_acl(path, tmp_path / "staged.acl") == expected_acl
            observed.append(path)
        return original(path, text, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", checked_write)
    writer(target, force=True)
    assert len(observed) == 1
    if os.name == "nt":
        assert _saved_acl(target, tmp_path / "published.acl") == expected_acl
    assert stat.S_IMODE(target.stat().st_mode) == previous_mode


def test_permission_copy_failure_preserves_existing_output(tmp_path, monkeypatch, writer):
    import cpdatakit._atomic as atomic

    target = tmp_path / "output.txt"
    target.write_bytes(b"previous complete output")

    def denied(*args):
        raise PermissionError("injected permission copy failure")

    if os.name == "nt":
        monkeypatch.setattr(atomic, "_copy_windows_dacl", denied)
    else:
        monkeypatch.setattr(os, "chown", denied)
    with pytest.raises((CPDataKitError, PermissionError), match="permission copy failure"):
        writer(target, force=True)
    assert target.read_bytes() == b"previous complete output"
    assert list(tmp_path.glob(".output.txt.*")) == []
