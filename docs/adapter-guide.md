# Adapter guide

An adapter translates one documented external representation into `Dataset`. Subclass
`cpdatakit.adapters.DatasetAdapter`, accept `pathlib.Path`, and return data plus explicit units and
conventions. A pure-Python reader with a focused, documented scope can live in the core package.
Readers that depend on solver runtimes or heavy format-specific libraries use an optional
package/extra. The current DAMASK reader is a focused core reader built on h5py.

## Registration and detection boundary

`DatasetAdapter.load(path)` remains the only required method. Existing subclasses that implement
only `load()` remain concrete. Optional class metadata is exposed through immutable `AdapterInfo`
values with a stable name, display format name, and capability labels. The default `detect()` returns
`False`, so detection is opt-in.

`AdapterRegistry` registers adapter classes, not instances. It can list descriptors, resolve a
stable name to a class, and return every detector matching a path. Callers construct the resolved
class themselves and supply format-specific scientific selections. Duplicate names are rejected.
`DEFAULT_ADAPTER_REGISTRY` contains the bundled DAMASK DADF5 adapter. This v0.5 boundary is
in-process only; it does not discover Python entry points or install plugins.

```python
from cpdatakit.adapters import DEFAULT_ADAPTER_REGISTRY

adapter_class = DEFAULT_ADAPTER_REGISTRY.get("damask-dadf5")
adapter = adapter_class(label="Taylor", datasets=["F", "P"])
dataset = adapter.load("result.hdf5")
```

Detection identifies a representation, not a valid or unambiguous scientific selection. A DADF5
file with multiple labels is detected as DADF5 and still requires the caller to choose a label.

## Acceptance checklist

An adapter proposal should satisfy every item before contribution:

- [ ] Official format evidence identifies the source specification, documentation, or reference
      implementation being supported.
- [ ] License and redistribution review confirms that the adapter and every fixture can be
      distributed under the project's terms.
- [ ] Upstream version coverage lists the tested source versions and documents unsupported ones.
- [ ] Synthetic or redistribution-approved fixtures cover the supported representation with a
      reproducible local test input.
- [ ] Units and scientific conventions are explicit, including identifiers, tensor component
      order, orientation representations, and stress/strain measures when relevant.
- [ ] Tests are deterministic and run offline with local fixtures, standard Python dependencies,
      and portable paths.
- [ ] Ambiguous or unsupported conventions return a clear error, and supported conventions are
      explicit in the adapter contract.
- [ ] Solver runtimes and other format-specific heavy dependencies are supplied through an
      optional package or extra.

Use the DADF5 label for the documented DAMASK hierarchy. An ODB adapter needs a legitimately
testable Abaqus environment and a matching acceptance record.

## DAMASK DADF5 reader

CPDataKit includes a documented read-only reader for selected DAMASK DADF5 results.
The implementation uses h5py directly and keeps the DAMASK runtime outside the package. It supports
DADF5 version 0.14 and 1.x, one explicit `increment`, `phase` or `homogenization` branch, one
explicit label, one field group, and selected direct datasets such as `F`, `P`, or `O`.

```python
from cpdatakit.adapters import DamaskDADF5Adapter

adapter = DamaskDADF5Adapter(
    increment=-1,
    kind="homogenization",
    label="Taylor",
    field="mechanical",
    datasets=["F", "P"],
)
dataset = adapter.load("result.hdf5")
```

The result is a CPDataKit `point` dataset. It adds a local `point_id` and places external values
under `user_dadf5_...` column names, preserving each dataset's `unit`, `description`, source
path, selected increment, and DADF5 version in metadata. A point ID is the row order within the
selected DADF5 group. Global cell mapping and scientific unit/tensor conventions are supplied by
the caller through the documented selection and schema. Missing metadata, ambiguous labels,
unsupported versions, and inconsistent record counts fail with `AdapterError`.

The format and hierarchy are based on the [official DAMASK DADF5 documentation](https://www.damask-mpie.de/documentation/reference/processing_tools/post-processing.html)
and [official license notice](https://damask-multiphysics.org/development/license.html). DAMASK
source code, solver output, and restricted fixtures remain at their upstream sources under their
original terms. DAMASK is an AGPLv3 project and its names remain the property of their respective
owners.

