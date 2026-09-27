"""Atomic publication of completed regular files on the same filesystem."""

from __future__ import annotations

import logging
import os
import stat
import sys
import uuid
from pathlib import Path

from .exceptions import CPDataKitError, OutputExistsError

logger = logging.getLogger(__name__)


def cleanup_staged_file(staged: str | Path) -> None:
    """Remove a staging name when possible, retaining and logging cleanup failures."""
    try:
        Path(staged).unlink(missing_ok=True)
    except OSError as exc:
        logger.warning("Retained staging file %s after cleanup failed: %s", staged, exc)


def publish_file(staged: str | Path, target: str | Path, *, force: bool = False) -> Path:
    """Publish a staged file, replacing an existing path only with explicit force.

    Without force, a hard link creates the destination atomically; a concurrent
    destination therefore cannot be overwritten. Both paths must be on the same
    filesystem with hard-link support. Publication failure retains the staged
    file; unsupported filesystems fail without copying. After publication,
    cleanup failure is logged and the extra staging name is retained.
    """
    staged, target = Path(staged), Path(target)
    if force:
        os.replace(staged, target)
    else:
        try:
            os.link(staged, target)
        except FileExistsError as exc:
            raise OutputExistsError(
                f"Output already exists: {target}; pass force=True to replace it"
            ) from exc
        except OSError as exc:
            raise CPDataKitError(
                "Cannot publish without overwriting: use a local filesystem with hard-link "
                "support and stage the file on the same filesystem as its output. "
                f"Original error: {exc}"
            ) from exc
        cleanup_staged_file(staged)
    return target


def write_text_atomic(target: str | Path, text: str, *, force: bool = False) -> Path:
    """Stage UTF-8 text with normal create permissions and publish it atomically."""
    target = Path(target)
    if target.exists() and not force:
        raise OutputExistsError(f"Output already exists: {target}; pass force=True to replace it")
    previous = target.stat() if target.exists() else None
    target.parent.mkdir(parents=True, exist_ok=True)
    staged = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
    # Exclusive creation applies the process umask just like Path.write_text.
    with staged.open("x", encoding="utf-8"):
        pass
    try:
        if previous is not None:
            if os.name == "nt":
                _copy_windows_dacl(target, staged)
            else:
                os.chown(staged, previous.st_uid, previous.st_gid)
            staged.chmod(stat.S_IMODE(previous.st_mode))
            if sys.platform.startswith("linux"):
                for name in os.listxattr(target):
                    if name == "system.posix_acl_access":
                        os.setxattr(staged, name, os.getxattr(target, name))
        staged.write_text(text, encoding="utf-8")
        return publish_file(staged, target, force=force)
    except BaseException:
        cleanup_staged_file(staged)
        raise


def _copy_windows_dacl(source: Path, target: Path) -> None:
    """Apply the existing DACL and inheritance policy before writing staged contents."""
    import ctypes
    from ctypes import wintypes

    security = ctypes.WinDLL("advapi32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    pointer = ctypes.c_void_p
    get_security = security.GetNamedSecurityInfoW
    get_security.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD] + [
        ctypes.POINTER(pointer)
    ] * 5
    get_security.restype = wintypes.DWORD
    set_security = security.SetNamedSecurityInfoW
    set_security.argtypes = [wintypes.LPWSTR, wintypes.DWORD, wintypes.DWORD] + [pointer] * 4
    set_security.restype = wintypes.DWORD
    get_control = security.GetSecurityDescriptorControl
    get_control.argtypes = [pointer, ctypes.POINTER(wintypes.WORD), ctypes.POINTER(wintypes.DWORD)]
    get_control.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [pointer]
    kernel.LocalFree.restype = pointer
    descriptor, dacl = pointer(), pointer()
    error = get_security(
        str(source), 1, 4, None, None, ctypes.byref(dacl), None, ctypes.byref(descriptor)
    )
    if error:
        raise ctypes.WinError(error)
    try:
        control, revision = wintypes.WORD(), wintypes.DWORD()
        if not get_control(descriptor, ctypes.byref(control), ctypes.byref(revision)):
            raise ctypes.WinError(ctypes.get_last_error())
        # SE_DACL_PROTECTED selects protected or inherited DACL publication.
        inheritance = 0x80000000 if control.value & 0x1000 else 0x20000000
        error = set_security(str(target), 1, 4 | inheritance, None, None, dacl, None)
        if error:
            raise ctypes.WinError(error)
    finally:
        kernel.LocalFree(descriptor)


def publish_directory(staged: str | Path, target: str | Path) -> Path:
    """Move a directory without replacing even an empty concurrent target.

    Uses Windows rename, Linux renameat2(RENAME_NOREPLACE), or macOS
    renamex_np(RENAME_EXCL). Other platforms fail safely instead of using POSIX
    rename, which could replace a user's empty destination directory.
    """
    staged, target = Path(staged), Path(target)
    try:
        if sys.platform == "win32":
            os.rename(staged, target)
        elif sys.platform.startswith("linux") or sys.platform == "darwin":
            import ctypes

            libc = ctypes.CDLL(None, use_errno=True)
            function = "renamex_np" if sys.platform == "darwin" else "renameat2"
            rename = getattr(libc, function, None)
            if rename is None:
                raise CPDataKitError(f"Atomic directory publication requires {function} support")
            if sys.platform == "darwin":
                # Apple xnu bsd/sys/stdio.h declares RENAME_EXCL = 0x00000004.
                rename.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
                arguments = (os.fsencode(staged), os.fsencode(target), 4)
            else:
                rename.argtypes = [
                    ctypes.c_int,
                    ctypes.c_char_p,
                    ctypes.c_int,
                    ctypes.c_char_p,
                    ctypes.c_uint,
                ]
                arguments = (-100, os.fsencode(staged), -100, os.fsencode(target), 1)
            rename.restype = ctypes.c_int
            if rename(*arguments):
                error = ctypes.get_errno()
                raise OSError(error, os.strerror(error), str(target))
        else:
            raise CPDataKitError(
                "Atomic directory publication requires Windows, Linux renameat2, or "
                "macOS renamex_np support; use a file output on this platform."
            )
    except FileExistsError as exc:
        raise OutputExistsError(f"Output already exists: {target}") from exc
    return target
