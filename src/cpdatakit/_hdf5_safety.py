"""Enforce the single-file provenance boundary before reading HDF5 payloads."""

from __future__ import annotations

import h5py

from .exceptions import DataReadError


def assert_self_contained_hdf5(handle: h5py.File) -> None:
    """Reject indirect storage without resolving it or reading dataset payloads.

    Inspect link declarations first, then only open hard-linked objects. Soft links
    are conservatively unsupported, including internal links: callers must not
    resolve dangling/cyclic links or a soft path that crosses an external link.
    Virtual datasets are unsupported even when their sources use the same file.
    Object addresses prevent repeated visits and terminate hard-link group cycles.
    The scan covers the entire file, including objects outside a selected field.
    """

    def reject(kind: str) -> None:
        # Do not expose a declared external filename or attempt to open it.
        raise DataReadError(
            f"HDF5 input must be self-contained: {kind} is unsupported. "
            "Create a separate self-contained copy with trusted tools before importing."
        )

    try:
        visited: set[int] = {h5py.h5o.get_info(handle.id).addr}
        pending: list[h5py.Group] = [handle]
        while pending:
            group = pending.pop()
            for name in group:
                link = group.get(name, getlink=True)
                if isinstance(link, h5py.ExternalLink):
                    reject("ExternalLink")
                if isinstance(link, h5py.SoftLink):
                    reject("SoftLink")
                if not isinstance(link, h5py.HardLink):
                    reject("unknown link type")
                item = group[name]
                address = h5py.h5o.get_info(item.id).addr
                if address in visited:
                    continue
                visited.add(address)
                if isinstance(item, h5py.Group):
                    pending.append(item)
                elif isinstance(item, h5py.Dataset):
                    properties = item.id.get_create_plist()
                    if properties.get_layout() == h5py.h5d.VIRTUAL:
                        reject("virtual dataset")
                    if properties.get_external_count():
                        reject("external raw storage")
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise DataReadError("Cannot verify that HDF5 input is self-contained") from exc
