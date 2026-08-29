# Adapter guide

An adapter translates one documented external representation into `Dataset`. Subclass
`cpdatakit.adapters.DatasetAdapter`, accept `pathlib.Path`, and return data plus explicit units and
conventions. Keep the integration in an optional package/extra; never add DAMASK, Abaqus, or a
commercial runtime to core dependencies.

## Acceptance checklist

An adapter proposal should satisfy every item before contribution:

- [ ] Official format evidence identifies the source specification, documentation, or reference
      implementation being supported.
- [ ] License and redistribution review confirms that the adapter and every fixture can be
      distributed under the project's terms.
- [ ] Upstream version coverage lists the tested source versions and documents unsupported ones.
- [ ] Synthetic or redistribution-approved fixtures cover the supported representation without
      requiring private or commercial data.
- [ ] Units and scientific conventions are explicit, including identifiers, tensor component
      order, orientation representations, and stress/strain measures when relevant.
- [ ] Tests are deterministic and run offline without network access, solver runtimes, GPUs, or
      personal filesystem paths.
- [ ] Ambiguous or unsupported conventions fail clearly instead of being inferred silently.
- [ ] Solver runtimes and other format-specific heavy dependencies stay out of CPDataKit core
      dependencies by using an optional package or extra.

Do not label a generic HDF5 reader as a DADF5 reader and do not claim ODB support without a
legitimately testable Abaqus environment.

## DAMASK DADF5 reader

CPDataKit includes a narrow, read-only reader for documented DAMASK DADF5 result selections.
The implementation uses h5py directly and does not require the DAMASK runtime. It supports
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
selected DADF5 group; the reader does not claim a global cell mapping or perform scientific
unit/tensor inference. Missing metadata, ambiguous labels, unsupported versions, and
inconsistent record counts fail with `AdapterError`.

The format and hierarchy are based on the [official DAMASK DADF5 documentation](https://www.damask-mpie.de/documentation/reference/processing_tools/post-processing.html)
and [official license notice](https://damask-multiphysics.org/development/license.html). CPDataKit
does not redistribute DAMASK source code, solver output, or restricted fixtures. DAMASK is an
AGPLv3 project and its names remain the property of their respective owners.

